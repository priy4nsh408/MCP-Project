import asyncio
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import mcp.server.stdio
import mcp.types as types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from database.connection import session_factory
from security.authentication import authenticate
from services.errors import BankingError, ValidationError
from services.write_service import WriteService


server = Server("Banking Write Server", version="0.1.0")
write_service = WriteService(session_factory)


def _transaction_properties(required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "account_id": {"type": "integer"},
            "transaction_id": {"type": "integer"},
            "transaction_date": {"type": "string", "format": "date"},
            "spending_category": {"type": "string"},
            "payment_channel": {"type": "string"},
            "transaction_type": {"type": "string", "enum": ["Debit", "Credit"]},
            "transaction_amount": {"type": "number", "exclusiveMinimum": 0},
            "confirmation": {"type": "string"},
            "email": {"type": "string", "format": "email"},
            "password": {"type": "string", "format": "password"},
        },
        "required": required,
    }


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="create_transaction",
            description="Create one transaction. Requires an authenticated writer or admin process.",
            inputSchema=_transaction_properties(
                [
                    "account_id",
                    "transaction_date",
                    "spending_category",
                    "payment_channel",
                    "transaction_type",
                    "transaction_amount",
                ]
            ),
        ),
        types.Tool(
            name="update_transaction",
            description="Update supplied fields on one transaction. Requires an authenticated writer or admin process.",
            inputSchema=_transaction_properties(["transaction_id"]),
        ),
        types.Tool(
            name="delete_transaction",
            description="Permanently delete one transaction. Requires authenticated admin access and explicit confirmation.",
            inputSchema=_transaction_properties(
                ["transaction_id", "confirmation"]
            ),
        ),
    ]


def _error_result(error: BankingError) -> types.CallToolResult:
    payload = {"error": {"code": error.code, "message": str(error)}}
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(payload))],
        structuredContent=payload,
        isError=True,
    )


def _parse_date(value: Any) -> date:
    if not isinstance(value, str):
        raise ValidationError("transaction_date must be an ISO date string")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValidationError("transaction_date must use YYYY-MM-DD") from error


def _parse_amount(value: Any) -> Decimal:
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValidationError("transaction_amount must be numeric") from error


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any] | types.CallToolResult:
    try:
        principal = authenticate(
            arguments.get("email"),
            arguments.get("password"),
            write_service.session_factory,
        )
        if name == "create_transaction":
            return write_service.create_transaction(
                principal,
                account_id=int(arguments["account_id"]),
                transaction_date=_parse_date(arguments["transaction_date"]),
                spending_category=str(arguments["spending_category"]),
                payment_channel=str(arguments["payment_channel"]),
                transaction_type=str(arguments["transaction_type"]),
                transaction_amount=_parse_amount(arguments["transaction_amount"]),
            )
        if name == "update_transaction":
            return write_service.update_transaction(
                principal,
                transaction_id=int(arguments["transaction_id"]),
                transaction_date=(
                    _parse_date(arguments["transaction_date"])
                    if "transaction_date" in arguments
                    else None
                ),
                spending_category=(
                    str(arguments["spending_category"])
                    if "spending_category" in arguments
                    else None
                ),
                payment_channel=(
                    str(arguments["payment_channel"])
                    if "payment_channel" in arguments
                    else None
                ),
                transaction_type=(
                    str(arguments["transaction_type"])
                    if "transaction_type" in arguments
                    else None
                ),
                transaction_amount=(
                    _parse_amount(arguments["transaction_amount"])
                    if "transaction_amount" in arguments
                    else None
                ),
            )
        if name == "delete_transaction":
            return write_service.delete_transaction(
                principal,
                transaction_id=int(arguments["transaction_id"]),
                confirmation=str(arguments.get("confirmation")),
            )
        raise ValidationError(f"unknown write tool: {name}")
    except BankingError as error:
        return _error_result(error)
    except (KeyError, TypeError, ValueError) as error:
        return _error_result(ValidationError(f"invalid tool arguments: {error}"))
    except Exception:
        return _error_result(ValidationError("unexpected write request failure"))


async def run() -> None:
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="banking-write-server",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(run())
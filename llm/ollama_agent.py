import asyncio
import ast
from datetime import date
import getpass
import json
import os
import re
from contextlib import AsyncExitStack
from decimal import Decimal
from typing import Any

from ollama import AsyncClient, ResponseError

from clients.dual_client import call_tool, connect_to_server


DEFAULT_MODEL = "mistral:latest"
MAX_TOOL_ROUNDS = 5
WRITE_TOOLS = {"create_transaction", "update_transaction", "delete_transaction"}

SYSTEM_PROMPT = """You are a banking assistant.

Use the available MCP tools for banking data. Never invent customer, account,
or transaction facts. Read tools are safe to use and never require an admin
email or password. Write tools change banking data and require the user's
explicit intent; never delete a transaction unless the user clearly confirms
the exact deletion request. Explain errors clearly.
Money values returned by tools are decimal strings; preserve their precision.
For any question about customers, accounts, or transactions, you MUST call the
appropriate MCP tool before answering. Do not return Python, JavaScript, or
pseudo-code showing how a tool could be called; execute the tool instead. Do
not describe what you are going to do, do not show hypothetical tool calls,
and do not ask for credentials for a read-only question.
Never invent an account ID or customer ID. If the user provides a customer
name but no account ID, call get_customer with the name first, then call
get_customer_accounts for each matching customer. Ask for clarification when
multiple customers match.
Write tools require the admin email and password on every call. When a write
tool is selected, the application will securely ask for those credentials;
never invent, print, or reuse credentials.
For a request to change a transaction amount, call update_transaction with
transaction_id and transaction_amount, plus the supplied admin email and
password. Do not add account_id unless the tool schema requires it. For other
transaction updates, pass only the fields the user asked to change.
For a total balance by customer name, call get_customer with the name, then
call get_customer_summary with each matching customer_id. Do not call
get_account_summary with a customer_id; that tool requires an account_id.
After all required read tools have returned, answer the user's question
directly and concisely. For a balance question, return the customer name,
account ID, account type, and balance. Do not include the tool workflow or
internal reasoning in the final answer.
"""


def _tool_schema(tool: Any) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "Banking MCP tool",
            "parameters": tool.inputSchema,
        },
    }


async def _discover_tool_schemas(
    read_session: Any, write_session: Any
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    read_tools = (await read_session.list_tools()).tools
    write_tools = (await write_session.list_tools()).tools
    schemas = [_tool_schema(tool) for tool in [*read_tools, *write_tools]]
    routing = {tool.name: read_session for tool in read_tools}
    routing.update({tool.name: write_session for tool in write_tools})
    return schemas, routing


def _message_dict(message: Any) -> dict[str, Any]:
    if hasattr(message, "model_dump"):
        return message.model_dump(exclude_none=True, by_alias=True)
    return dict(message)


def _tool_call_dict(tool_call: Any) -> dict[str, Any]:
    if hasattr(tool_call, "model_dump"):
        return tool_call.model_dump(exclude_none=True, by_alias=True)
    return dict(tool_call)


def _textual_tool_calls(content: str, known_tools: set[str]) -> list[dict[str, Any]]:
    """Parse only JSON tool-call text emitted by models without native calls."""
    prose_call = re.search(
        r"(?:call the\s+)?[`']?([A-Za-z0-9_]+)[`']?\s+(?:function|tool)\b",
        content,
        re.I,
    )
    if prose_call and prose_call.group(1) in known_tools:
        tool_name = prose_call.group(1)
        arguments: dict[str, Any] = {}
        for field in (
            "transaction_id",
            "transaction_amount",
            "account_id",
            "customer_id",
        ):
            value = re.search(
                rf"[`']?{field}[`']?\s*:\s*([-+]?\d+(?:\.\d+)?)\b",
                content,
                re.I,
            )
            if value:
                arguments[field] = (
                    float(value.group(1))
                    if "." in value.group(1)
                    else int(value.group(1))
                )
        if "transaction_id" not in arguments:
            value = re.search(
                r"transaction\s+(?:id|number)\s*(?:is|=|:)?\s*(\d+)\b",
                content,
                re.I,
            )
            if value:
                arguments["transaction_id"] = int(value.group(1))
        if "transaction_amount" not in arguments:
            value = re.search(
                r"(?:new\s+)?(?:transaction\s+)?amount\b[\s\S]{0,100}?"
                r"(\d+\.\d+)\b",
                content,
                re.I,
            )
            if value:
                arguments["transaction_amount"] = float(value.group(1))
        if arguments:
            return [{"function": {"name": tool_name, "arguments": arguments}}]

    named_call = re.search(
        r'"name"\s*:\s*"([A-Za-z0-9_]+)"[\s\S]*?'
        r'"arguments"\s*:\s*(\{[^{}]*\})',
        content,
    )
    if named_call and named_call.group(1) in known_tools:
        try:
            arguments = json.loads(named_call.group(2))
        except json.JSONDecodeError:
            arguments = None
        if isinstance(arguments, dict):
            return [
                {
                    "function": {
                        "name": named_call.group(1),
                        "arguments": arguments,
                    }
                }
            ]

    candidates = re.findall(r"```(?:json)?\s*([\s\S]*?)```", content)
    candidates.extend(re.findall(r"\[[\s\S]*?\]", content))
    candidates.extend(re.findall(r"\{\s*\"name\"[\s\S]*?\}", content))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            parsed = [parsed]
        if not isinstance(parsed, list):
            continue
        calls = []
        for item in parsed:
            if not isinstance(item, dict):
                calls = []
                break
            name = item.get("name")
            arguments = item.get("arguments", {})
            if name not in known_tools or not isinstance(arguments, dict):
                calls = []
                break
            calls.append({"function": {"name": name, "arguments": arguments}})
        if calls:
            return calls

    for match in re.finditer(r"\b([A-Za-z0-9_]+)\s*\([^\n]*\)", content):
        if match.group(1) not in known_tools:
            continue
        try:
            expression = ast.parse(match.group(0), mode="eval").body
        except SyntaxError:
            continue
        if (
            not isinstance(expression, ast.Call)
            or not isinstance(expression.func, ast.Name)
            or expression.args
        ):
            continue
        try:
            arguments = {
                keyword.arg: ast.literal_eval(keyword.value)
                for keyword in expression.keywords
                if keyword.arg is not None
            }
        except (ValueError, SyntaxError):
            continue
        if len(arguments) == len(expression.keywords):
            return [
                {
                    "function": {
                        "name": expression.func.id,
                        "arguments": arguments,
                    }
                }
            ]

    for match in re.finditer(
        r"\b([A-Za-z0-9_]+)\s*\(([^)]*)\)", content, re.I | re.S
    ):
        if match.group(1) not in known_tools:
            continue
        arguments = {}
        for field in (
            "transaction_id",
            "transaction_amount",
            "account_id",
            "customer_id",
        ):
            value = re.search(
                rf"\b{field}\s*=\s*([-+]?\d+(?:\.\d+)?)\b",
                match.group(2),
                re.I,
            )
            if value:
                arguments[field] = (
                    float(value.group(1))
                    if "." in value.group(1)
                    else int(value.group(1))
                )
        if arguments:
            return [
                {
                    "function": {
                        "name": match.group(1),
                        "arguments": arguments,
                    }
                }
            ]
    return []


def _exception_message(error: BaseException) -> str:
    if isinstance(error, BaseExceptionGroup) and error.exceptions:
        messages = [_exception_message(child) for child in error.exceptions]
        return "; ".join(message for message in messages if message)
    return str(error) or type(error).__name__


def _has_explicit_account_id(prompt: str) -> bool:
    return re.search(r"\baccount(?:\s+(?:id|number))?\s*(?:#|is|=)?\s*\d+\b", prompt, re.I) is not None


def _requires_customer_resolution(prompt: str, tool_name: str) -> bool:
    return tool_name in {"get_account", "get_account_summary"} and not _has_explicit_account_id(prompt)


def _account_id_for_balance(prompt: str) -> int | None:
    if not re.search(r"\bbalance\b", prompt, re.I):
        return None
    match = re.search(
        r"\baccount(?:\s+(?:id|number))?\s*(?:#|is|=)?\s*(\d+)\b",
        prompt,
        re.I,
    )
    return int(match.group(1)) if match else None


def _looks_like_unexecuted_plan(content: str) -> bool:
    """Identify code or workflow instructions returned instead of an answer."""
    return (
        "```" in content
        or bool(re.search(r"\b(?:for|while)\s+\w+\s+in\s+", content, re.I))
        or bool(re.search(r"\bget_(?:account|customer)(?:_summary)?\s*\(", content))
        or "return f" in content
    )


def _customer_name_for_total_balance(prompt: str) -> str | None:
    if not re.search(
        r"\btotal\s+(?:(?:account|bank)\s+)?b(?:alance|anlance)\b",
        prompt,
        re.I,
    ):
        return None
    match = re.search(
        r"\b(?:in|for|of|is(?!\s+the\b))\s+"
        r"([A-Za-z][A-Za-z'-]*(?:\s+[A-Za-z][A-Za-z'-]*)*?)"
        r"(?=\s+(?:total|account|bank|balance|banlance)\b|[?.!,]|$)",
        prompt,
        re.I,
    )
    return match.group(1).strip() if match else None


def _customer_name_for_total_savings(prompt: str) -> str | None:
    if not re.search(r"\btotal\s+savings\b", prompt, re.I):
        return None
    match = re.search(
        r"\b(?:in|for|of|is(?!\s+the\b))\s+"
        r"([A-Za-z][A-Za-z'-]*(?:\s+[A-Za-z][A-Za-z'-]*)*?)"
        r"(?:'s)?(?=\s+(?:account|savings)\b|[?.!,]|$)",
        prompt,
        re.I,
    )
    return re.sub(r"'s$", "", match.group(1).strip()) if match else None


def _customer_name_for_details(prompt: str) -> str | None:
    match = re.search(
        r"\bcustomer\s+(?:details|information|info)\s+(?:of|for)\s+"
        r"([A-Za-z][A-Za-z'-]*(?:\s+[A-Za-z][A-Za-z'-]*)*)\s*[?.!,]*$",
        prompt.strip(),
        re.I,
    )
    return match.group(1).strip() if match else None


def _transaction_amount_update_request(prompt: str) -> tuple[int, Decimal] | None:
    if not re.search(r"\b(?:change|update|set)\b", prompt, re.I):
        return None
    transaction_match = re.search(
        r"transaction[_\s-]*(?:id|number)?\s*(?:is|=|:)?\s*(\d+)\b",
        prompt,
        re.I,
    )
    amount_match = re.search(
        r"\b(?:to|amount\s+(?:to|as)|new\s+amount\s*(?:is|=|:)?)[\s$]*"
        r"(\d+(?:\.\d{1,2})?)\b",
        prompt,
        re.I,
    )
    if not transaction_match or not amount_match:
        return None
    return int(transaction_match.group(1)), Decimal(amount_match.group(1))


def _transaction_summary_request(
    prompt: str,
) -> tuple[str, str, str | None] | None:
    if not re.search(r"\btransactions?\b|\btransaction\s+amount\b", prompt, re.I):
        return None
    dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", prompt)
    if len(dates) < 2:
        return None
    try:
        parsed_dates = [date.fromisoformat(value) for value in dates[:2]]
    except ValueError:
        return None
    transaction_type_match = re.search(r"\b(debit|credit)\b", prompt, re.I)
    transaction_type = (
        transaction_type_match.group(1).capitalize()
        if transaction_type_match
        else None
    )
    return dates[0], dates[1], transaction_type


async def _resolve_transaction_summary(
    prompt: str, read_session: Any, routing: dict[str, Any]
) -> str | None:
    request = _transaction_summary_request(prompt)
    if request is None or "transaction_summary" not in routing:
        return None
    start_date, end_date, transaction_type = request
    result = await call_tool(
        read_session,
        "transaction_summary",
        {
            "start_date": start_date,
            "end_date": end_date,
            **({"transaction_type": transaction_type} if transaction_type else {}),
        },
    )
    payload = result.get("result", result) if isinstance(result, dict) else result
    if not isinstance(payload, dict):
        return str(payload)
    lines = [
        f"Transaction totals from {payload['start_date']} to {payload['end_date']}:",
        f"Total transactions: {payload['transaction_count']}",
        f"Total transaction amount: ${payload['total_transaction_amount']}",
    ]
    for kind in ("Debit", "Credit"):
        details = payload.get("by_transaction_type", {}).get(kind)
        if details is not None:
            lines.append(
                f"{kind}: {details['transaction_count']} transactions, "
                f"${details['total_transaction_amount']}"
            )
    if transaction_type:
        lines.insert(1, f"Transaction type: {transaction_type}")
    return "\n".join(lines)


async def _resolve_account_balance(
    prompt: str, read_session: Any, routing: dict[str, Any]
) -> str | None:
    account_id = _account_id_for_balance(prompt)
    if account_id is None or "get_account" not in routing:
        return None
    result = await call_tool(read_session, "get_account", {"account_id": account_id})
    account = result.get("result", result) if isinstance(result, dict) else result
    if not isinstance(account, dict):
        return str(account)
    return (
        f"Account ID: {account['account_id']}\n"
        f"Account type: {account['account_type']}\n"
        f"Balance: ${account['account_balance']}"
    )


async def _resolve_total_balance(
    prompt: str, read_session: Any, routing: dict[str, Any]
) -> str | None:
    customer_name = _customer_name_for_total_balance(prompt)
    if not customer_name or "get_customer_accounts" not in routing:
        return None
    customer_result = await call_tool(
        read_session, "get_customer", {"name": customer_name}
    )
    customers = (
        customer_result.get("result", customer_result)
        if isinstance(customer_result, dict)
        else customer_result
    )
    if not isinstance(customers, list) or not customers:
        return None
    total = Decimal("0.00")
    customer_lines: list[str] = []
    for customer in customers:
        if not isinstance(customer, dict) or "customer_id" not in customer:
            continue
        account_result = await call_tool(
            read_session,
            "get_customer_accounts",
            {"customer_id": customer["customer_id"]},
        )
        accounts = (
            account_result.get("result", account_result)
            if isinstance(account_result, dict)
            else account_result
        )
        if not isinstance(accounts, list):
            continue
        customer_lines.append(f"Customer ID {customer['customer_id']}:")
        for account in accounts:
            if not isinstance(account, dict):
                continue
            balance = Decimal(str(account["account_balance"]))
            total += balance
            customer_lines.append(
                f"  Account ID {account['account_id']} "
                f"({account['account_type']}): ${balance:f}"
            )
    if not customer_lines:
        return None
    details = "\n".join(customer_lines)
    return f"{details}\nTotal balance for {customer_name}: ${total:f}"


async def _resolve_total_savings(
    prompt: str, read_session: Any, routing: dict[str, Any]
) -> str | None:
    customer_name = _customer_name_for_total_savings(prompt)
    if not customer_name or "get_customer_accounts" not in routing:
        return None
    customer_result = await call_tool(
        read_session, "get_customer", {"name": customer_name}
    )
    customers = (
        customer_result.get("result", customer_result)
        if isinstance(customer_result, dict)
        else customer_result
    )
    if not isinstance(customers, list) or not customers:
        return None
    total = Decimal("0.00")
    customer_lines: list[str] = []
    for customer in customers:
        if not isinstance(customer, dict) or "customer_id" not in customer:
            continue
        account_result = await call_tool(
            read_session,
            "get_customer_accounts",
            {"customer_id": customer["customer_id"], "account_type": "Savings"},
        )
        accounts = (
            account_result.get("result", account_result)
            if isinstance(account_result, dict)
            else account_result
        )
        if not isinstance(accounts, list):
            continue
        customer_lines.append(f"Customer ID {customer['customer_id']}:")
        for account in accounts:
            if not isinstance(account, dict):
                continue
            balance = Decimal(str(account["account_balance"]))
            total += balance
            customer_lines.append(
                f"  Account ID {account['account_id']} (Savings): ${balance:f}"
            )
    if not customer_lines:
        return None
    details = "\n".join(customer_lines)
    return f"{details}\nTotal savings for {customer_name}: ${total:f}"


async def _resolve_customer_details(
    prompt: str, read_session: Any, routing: dict[str, Any]
) -> str | None:
    customer_name = _customer_name_for_details(prompt)
    if not customer_name or "get_customer" not in routing:
        return None
    result = await call_tool(read_session, "get_customer", {"name": customer_name})
    customers = result.get("result", result) if isinstance(result, dict) else result
    if not isinstance(customers, list):
        return str(customers)
    if not customers:
        return f"No customers matched {customer_name}."
    if len(customers) > 1:
        lines = [f"Multiple customers match {customer_name}:"]
        lines.extend(
            f"Customer ID {customer['customer_id']}: {customer['customer_name']} "
            f"({customer['branch']})"
            for customer in customers
        )
        return "\n".join(lines)
    customer = customers[0]
    return (
        f"Customer ID: {customer['customer_id']}\n"
        f"Customer name: {customer['customer_name']}\n"
        f"Branch: {customer['branch']}"
    )


async def _execute_transaction_amount_update(
    prompt: str,
    write_session: Any,
    routing: dict[str, Any],
    credential_provider: Any | None,
) -> str | None:
    request = _transaction_amount_update_request(prompt)
    if request is None or "update_transaction" not in routing:
        return None
    if credential_provider is None:
        return "Admin email and password are required for this write request."
    credentials = credential_provider()
    if hasattr(credentials, "__await__"):
        credentials = await credentials
    result = await call_tool(
        write_session,
        "update_transaction",
        {
            "transaction_id": request[0],
            "transaction_amount": float(request[1]),
            "email": str(credentials["email"]).strip(),
            "password": str(credentials["password"]),
        },
    )
    payload = result.get("result", result) if isinstance(result, dict) else result
    if isinstance(payload, dict) and payload.get("transaction_id") is not None:
        return (
            f"Transaction {payload['transaction_id']} updated successfully. "
            f"New transaction amount: ${payload['transaction_amount']}"
        )
    return str(payload)


async def ask_banking(
    prompt: str,
    *,
    model: str | None = None,
    max_tool_rounds: int = MAX_TOOL_ROUNDS,
    ollama_client: AsyncClient | None = None,
    credential_provider: Any | None = None,
) -> str:
    """Ask Mistral a banking question and let it call the MCP servers."""
    selected_model = model or os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL)
    client = ollama_client or AsyncClient(
        host=os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    )
    async with AsyncExitStack() as stack:
        read_session = await stack.enter_async_context(
            connect_to_server("servers.read_server")
        )
        write_session = await stack.enter_async_context(
            connect_to_server("servers.write_server")
        )
        tools, routing = await _discover_tool_schemas(read_session, write_session)
        resolved_transaction_summary = await _resolve_transaction_summary(
            prompt, read_session, routing
        )
        if resolved_transaction_summary is not None:
            return resolved_transaction_summary
        resolved_account_balance = await _resolve_account_balance(
            prompt, read_session, routing
        )
        if resolved_account_balance is not None:
            return resolved_account_balance
        resolved_total_balance = await _resolve_total_balance(
            prompt, read_session, routing
        )
        if resolved_total_balance is not None:
            return resolved_total_balance
        resolved_total_savings = await _resolve_total_savings(
            prompt, read_session, routing
        )
        if resolved_total_savings is not None:
            return resolved_total_savings
        resolved_customer_details = await _resolve_customer_details(
            prompt, read_session, routing
        )
        if resolved_customer_details is not None:
            return resolved_customer_details
        resolved_update = await _execute_transaction_amount_update(
            prompt, write_session, routing, credential_provider
        )
        if resolved_update is not None:
            return resolved_update
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Execute the appropriate MCP tool calls now. For a read "
                    "request, use read tools; for a write request, use the "
                    "matching write tool. Do not reply with a plan, explanation, "
                    "or hypothetical call. After the tool results, answer only "
                    "the user's request. For a write request, emit the write "
                    "tool call even if email/password are not present; the "
                    "application will collect them securely. Request: "
                    + prompt
                ),
            },
        ]
        resolved_account_ids: set[int] = set()
        write_credentials: dict[str, str] | None = None

        for round_number in range(max_tool_rounds):
            try:
                response = await client.chat(
                    model=selected_model,
                    messages=messages,
                    tools=tools,
                )
            except ResponseError as error:
                if error.status_code == 404:
                    raise RuntimeError(
                        f"Ollama model {selected_model!r} is unavailable. "
                        f"Run: ollama pull {selected_model}"
                    ) from error
                raise RuntimeError(f"Ollama request failed: {error.error}") from error

            assistant_message = _message_dict(response.message)
            messages.append(assistant_message)
            tool_calls = assistant_message.get("tool_calls", [])
            if not tool_calls:
                tool_calls = _textual_tool_calls(
                    assistant_message.get("content", ""), set(routing)
                )
            if tool_calls:
                assistant_message["tool_calls"] = tool_calls
            if not tool_calls:
                if round_number == 0:
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "You did not call an MCP tool. Call the appropriate "
                                "read or write tool now; do not provide a plan, "
                                "code, or an unverified answer. Read tools need "
                                "no credentials. Write tools need the user's "
                                "email and password; the application will ask "
                                "for them securely."
                            ),
                        }
                    )
                    continue
                if _looks_like_unexecuted_plan(assistant_message.get("content", "")):
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "That was not a final answer. Execute the MCP tools "
                                "now. For a customer total balance, call "
                                "get_customer_summary for every matching customer_id; "
                                "do not return code, a prompt, or a workflow. Then "
                                "return only the calculated answer."
                            ),
                        }
                    )
                    continue
                return assistant_message.get("content", "")

            for raw_tool_call in tool_calls:
                tool_call = _tool_call_dict(raw_tool_call)
                function = tool_call.get("function", {})
                name = function.get("name")
                arguments = function.get("arguments", {})
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                if (
                    name == "get_account_summary"
                    and "account_id" not in arguments
                    and "customer_id" in arguments
                    and "get_customer_summary" in routing
                ):
                    name = "get_customer_summary"
                session = routing.get(name)
                account_id = arguments.get("account_id")
                if (
                    _requires_customer_resolution(prompt, name)
                    and account_id not in resolved_account_ids
                ):
                    tool_result = {
                        "error": (
                            "No account ID was provided. Do not invent one. "
                            "Call get_customer with the customer's name first."
                        )
                    }
                elif session is None:
                    tool_result = {"error": f"Unknown MCP tool: {name}"}
                else:
                    try:
                        if name in WRITE_TOOLS:
                            if write_credentials is None:
                                if credential_provider is None:
                                    tool_result = {
                                        "error": (
                                            "Admin email and password are required "
                                            "for this write call."
                                        )
                                    }
                                else:
                                    credentials = credential_provider()
                                    if hasattr(credentials, "__await__"):
                                        credentials = await credentials
                                    write_credentials = {
                                        "email": str(credentials["email"]).strip(),
                                        "password": str(credentials["password"]),
                                    }
                            if write_credentials is not None:
                                arguments = {**arguments, **write_credentials}
                                tool_result = await call_tool(session, name, arguments)
                        else:
                            tool_result = await call_tool(session, name, arguments)
                        if name == "get_customer_accounts" and isinstance(tool_result, list):
                            resolved_account_ids.update(
                                account["account_id"]
                                for account in tool_result
                                if isinstance(account, dict)
                                and isinstance(account.get("account_id"), int)
                            )
                    except RuntimeError as error:
                        if "AUTHENTICATION_FAILED" in str(error):
                            return f"Write request failed: {error}"
                        tool_result = {"error": str(error)}
                messages.append(
                    {
                        "role": "tool",
                        "tool_name": name,
                        "content": json.dumps(tool_result, default=str),
                    }
                )

        raise RuntimeError(
            f"Mistral exceeded the maximum of {max_tool_rounds} MCP tool rounds"
        )


async def run_interactive(
    ask_function: Any = ask_banking,
    input_function: Any = input,
) -> None:
    def prompt_for_credentials() -> dict[str, str]:
        email = input_function("Admin email: ").strip()
        password = getpass.getpass("Admin password: ")
        return {"email": email, "password": password}

    print("Banking assistant ready. Type 'exit' to close.")
    while True:
        try:
            prompt = input_function("Banking question: ").strip()
        except EOFError:
            print("\nInput closed. Type 'exit' during an interactive session to stop.")
            return

        if prompt.lower() == "exit":
            print("Goodbye.")
            return
        if not prompt:
            continue

        try:
            if ask_function is ask_banking:
                answer = await ask_function(
                    prompt, credential_provider=prompt_for_credentials
                )
            else:
                answer = await ask_function(prompt)
            print(f"\n{answer}\n")
        except Exception as error:
            print(f"Error: {_exception_message(error)}")


async def main_async() -> None:
    await run_interactive()


def main() -> None:
    try:
        asyncio.run(main_async())
    except RuntimeError as error:
        print(f"Error: {error}")


if __name__ == "__main__":
    main()
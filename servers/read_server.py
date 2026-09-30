from contextlib import contextmanager
from decimal import Decimal
from typing import Any, Iterator

from mcp.server.fastmcp import FastMCP

from database.connection import session_factory
from services.account_service import AccountService
from services.customer_service import CustomerService
from services.errors import BankingError
from services.transaction_service import TransactionService


mcp = FastMCP(
    "Banking Read Server",
    instructions="Read-only banking data tools. No tool on this server changes data.",
)


@contextmanager
def service_bundle() -> Iterator[tuple[CustomerService, AccountService, TransactionService]]:
    from repositories.account_repository import AccountRepository
    from repositories.customer_repository import CustomerRepository
    from repositories.transaction_repository import TransactionRepository

    with session_factory() as session:
        customer_repository = CustomerRepository(session)
        account_repository = AccountRepository(session)
        transaction_repository = TransactionRepository(session)
        yield (
            CustomerService(
                customer_repository, account_repository, transaction_repository
            ),
            AccountService(account_repository, transaction_repository),
            TransactionService(
                transaction_repository, account_repository, customer_repository
            ),
        )


def _decimal(value: Decimal) -> str:
    return format(value, "f")


def _error_message(error: BankingError) -> ValueError:
    return ValueError(f"{error.code}: {error}")


def _customer_dict(customer: Any) -> dict[str, Any]:
    return {
        "customer_id": customer.customer_id,
        "customer_name": customer.customer_name,
        "branch": customer.branch,
    }


def _account_dict(account: Any) -> dict[str, Any]:
    return {
        "account_id": account.account_id,
        "customer_id": account.customer_id,
        "account_type": account.account_type,
        "account_balance": _decimal(account.account_balance),
    }


def _transaction_dict(transaction: Any) -> dict[str, Any]:
    return {
        "transaction_id": transaction.transaction_id,
        "account_id": transaction.account_id,
        "transaction_date": transaction.transaction_date.isoformat(),
        "spending_category": transaction.spending_category,
        "payment_channel": transaction.payment_channel,
        "transaction_type": transaction.transaction_type,
        "transaction_amount": _decimal(transaction.transaction_amount),
    }


def _summary_dict(summary: Any) -> dict[str, Any]:
    transaction_summary = summary.transaction_summary
    result = {
        "transaction_count": transaction_summary.transaction_count,
        "debit_count": transaction_summary.debit_count,
        "credit_count": transaction_summary.credit_count,
        "debit_total": _decimal(transaction_summary.debit_total),
        "credit_total": _decimal(transaction_summary.credit_total),
        "average_amount": _decimal(transaction_summary.average_amount),
    }
    return result


@mcp.tool()
def get_customer(
    customer_id: int | None = None,
    name: str | None = None,
    branch: str | None = None,
    limit: int | None = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    """Return a customer by ID or filtered matching customers. Read-only."""
    try:
        with service_bundle() as (customer_service, _, _):
            if customer_id is not None and any(
                value is not None for value in (name, branch, limit)
            ):
                raise ValueError("customer_id cannot be combined with filters")
            if customer_id is not None:
                return _customer_dict(customer_service.get_customer(customer_id))
            if name is None and branch is None:
                raise ValueError("customer_id, name, or branch is required")
            customers = customer_service.find_customers(
                name=name, branch=branch, limit=limit
            )
            return [_customer_dict(c) for c in customers]
    except BankingError as error:
        raise _error_message(error) from error


@mcp.tool()
def get_customer_accounts(
    customer_id: int, account_type: str | None = None, limit: int | None = None
) -> list[dict[str, Any]]:
    """Return a customer's accounts with optional type and count filters."""
    try:
        with service_bundle() as (customer_service, _, _):
            return [
                _account_dict(account)
                for account in customer_service.get_customer_accounts(
                    customer_id, account_type=account_type, limit=limit
                )
            ]
    except BankingError as error:
        raise _error_message(error) from error


@mcp.tool()
def get_account(account_id: int) -> dict[str, Any]:
    """Return one account by ID, including its current balance. Read-only."""
    try:
        with service_bundle() as (_, account_service, _):
            return _account_dict(account_service.get_account(account_id))
    except BankingError as error:
        raise _error_message(error) from error


@mcp.tool()
def get_account_transactions(
    account_id: int,
    limit: int = 100,
    offset: int = 0,
    transaction_type: str | None = None,
    spending_category: str | None = None,
    payment_channel: str | None = None,
) -> list[dict[str, Any]]:
    """Return filtered, dated transactions for an account. Read-only."""
    try:
        with service_bundle() as (_, account_service, _):
            return [
                _transaction_dict(transaction)
                for transaction in account_service.get_account_transactions(
                    account_id, limit=limit, offset=offset,
                    transaction_type=transaction_type,
                    spending_category=spending_category,
                    payment_channel=payment_channel,
                )
            ]
    except BankingError as error:
        raise _error_message(error) from error


@mcp.tool()
def get_customer_transactions(
    customer_id: int,
    limit: int = 100,
    offset: int = 0,
    transaction_type: str | None = None,
    spending_category: str | None = None,
    payment_channel: str | None = None,
) -> list[dict[str, Any]]:
    """Return filtered customer transactions with pagination. Read-only."""
    try:
        with service_bundle() as (_, _, transaction_service):
            return [
                _transaction_dict(transaction)
                for transaction in transaction_service.get_customer_transactions(
                    customer_id, limit=limit, offset=offset,
                    transaction_type=transaction_type,
                    spending_category=spending_category,
                    payment_channel=payment_channel,
                )
            ]
    except BankingError as error:
        raise _error_message(error) from error


@mcp.tool()
def transaction_summary(
    start_date: str, end_date: str, transaction_type: str | None = None
) -> dict[str, Any]:
    """Return transaction totals for an inclusive date range, optionally filtered by type."""
    try:
        from datetime import date

        parsed_start_date = date.fromisoformat(start_date)
        parsed_end_date = date.fromisoformat(end_date)
        with service_bundle() as (_, _, transaction_service):
            summary = transaction_service.get_transaction_summary(
                parsed_start_date, parsed_end_date, transaction_type=transaction_type
            )
            result = {
                **summary,
                "total_transaction_amount": _decimal(
                    summary["total_transaction_amount"]
                ),
            }
            result["by_transaction_type"] = {
                transaction_kind: {
                    "transaction_count": values["transaction_count"],
                    "total_transaction_amount": _decimal(
                        values["total_transaction_amount"]
                    ),
                }
                for transaction_kind, values in summary["by_transaction_type"].items()
            }
            return result
    except ValueError as error:
        if isinstance(error, BankingError):
            raise _error_message(error) from error
        raise ValueError("start_date and end_date must use YYYY-MM-DD") from error
    except BankingError as error:
        raise _error_message(error) from error


@mcp.tool()
def get_account_summary(account_id: int) -> dict[str, Any]:
    """Return debit, credit, average, and top spending data for an account. Read-only."""
    try:
        with service_bundle() as (_, account_service, _):
            summary = account_service.get_account_summary(account_id)
            return {
                "account_id": summary.account_id,
                "customer_id": summary.customer_id,
                "account_type": summary.account_type,
                "account_balance": _decimal(summary.account_balance),
                "transaction_summary": _summary_dict(summary),
                "top_spending_categories": [
                    {
                        "category": category.category,
                        "debit_total": _decimal(category.debit_total),
                    }
                    for category in summary.top_spending_categories
                ],
            }
    except BankingError as error:
        raise _error_message(error) from error


@mcp.tool()
def get_customer_summary(customer_id: int) -> dict[str, Any]:
    """Return customer identity, account count, balance, and activity totals. Read-only."""
    try:
        with service_bundle() as (customer_service, _, _):
            summary = customer_service.get_customer_summary(customer_id)
            return {
                "customer_id": summary.customer_id,
                "customer_name": summary.customer_name,
                "branch": summary.branch,
                "account_count": summary.account_count,
                "total_balance": _decimal(summary.total_balance),
                "transaction_summary": _summary_dict(summary),
            }
    except BankingError as error:
        raise _error_message(error) from error


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
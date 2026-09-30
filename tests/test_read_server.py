import asyncio

import pytest

from servers.read_server import (
    get_account,
    get_account_transactions,
    get_customer,
    get_customer_accounts,
    get_customer_transactions,
    get_customer_summary,
    mcp,
    transaction_summary,
)


def test_read_tools_are_registered_and_return_structured_data() -> None:
    tools = asyncio.run(mcp.list_tools())
    tool_names = {tool.name for tool in tools}

    assert tool_names == {
        "get_customer",
        "get_customer_accounts",
        "get_account",
        "get_account_transactions",
        "get_customer_transactions",
        "get_account_summary",
        "get_customer_summary",
        "transaction_summary",
    }
    assert get_account(1)["account_id"] == 1
    assert len(get_account_transactions(1, limit=2)) == 2
    assert get_customer_summary(1)["account_count"] >= 1


def test_transaction_summary_totals_amounts_inclusive_date_range() -> None:
    result = transaction_summary("2025-01-01", "2025-01-01")

    assert result["start_date"] == "2025-01-01"
    assert result["end_date"] == "2025-01-01"
    assert result["transaction_count"] > 0
    assert result["total_transaction_amount"] != "0.00"


def test_read_server_translates_missing_records() -> None:
    with pytest.raises(ValueError, match="ACCOUNT_NOT_FOUND"):
        get_account(999999)


def test_read_tools_apply_filters() -> None:
    customers = get_customer(branch="Delhi", limit=2)
    assert len(customers) == 2
    assert all(customer["branch"] == "Delhi" for customer in customers)

    accounts = get_customer_accounts(1, account_type="Savings")
    assert all(account["account_type"] == "Savings" for account in accounts)

    transactions = get_account_transactions(
        1, transaction_type="Debit", spending_category="Groceries"
    )
    assert transactions
    assert all(
        transaction["transaction_type"] == "Debit"
        and transaction["spending_category"] == "Groceries"
        for transaction in transactions
    )

    customer_transactions = get_customer_transactions(
        1, payment_channel="UPI", limit=3
    )
    assert len(customer_transactions) <= 3
    assert all(transaction["payment_channel"] == "UPI" for transaction in customer_transactions)
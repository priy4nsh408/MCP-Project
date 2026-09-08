import asyncio

import pytest

from servers.read_server import (
    get_account,
    get_account_transactions,
    get_customer_summary,
    mcp,
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
    }
    assert get_account(1)["account_id"] == 1
    assert len(get_account_transactions(1, limit=2)) == 2
    assert get_customer_summary(1)["account_count"] >= 1


def test_read_server_translates_missing_records() -> None:
    with pytest.raises(ValueError, match="ACCOUNT_NOT_FOUND"):
        get_account(999999)
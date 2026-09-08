import asyncio

from clients.dual_client import run_demo


def test_dual_client_discovers_both_servers_and_reads_data() -> None:
    result = asyncio.run(run_demo())

    assert "get_account_summary" in result["read_tools"]
    assert result["write_tools"] == [
        "create_transaction",
        "update_transaction",
        "delete_transaction",
    ]
    assert result["account_summary"]["account_id"] == 1
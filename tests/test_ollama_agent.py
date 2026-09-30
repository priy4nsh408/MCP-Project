from decimal import Decimal
from types import SimpleNamespace

from llm.ollama_agent import (
    DEFAULT_MODEL,
    SYSTEM_PROMPT,
    _message_dict,
    _tool_call_dict,
    _tool_schema,
    _textual_tool_calls,
    _has_explicit_account_id,
    _account_id_for_balance,
    _customer_name_for_total_balance,
    _customer_name_for_total_savings,
    _customer_name_for_details,
    _transaction_amount_update_request,
    _transaction_summary_request,
    _looks_like_unexecuted_plan,
    _requires_customer_resolution,
)


def test_system_prompt_requires_read_tool_execution_and_concise_answers() -> None:
    assert "Read tools are safe to use and never require" in SYSTEM_PROMPT
    assert "describe what you are going" in SYSTEM_PROMPT
    assert "hypothetical tool calls" in SYSTEM_PROMPT
    assert "answer the user's question" in SYSTEM_PROMPT
    assert "directly and concisely" in SYSTEM_PROMPT
    assert "call update_transaction with" in SYSTEM_PROMPT
    assert "Do not add account_id" in SYSTEM_PROMPT


def test_default_model_matches_local_ollama_tag() -> None:
    assert DEFAULT_MODEL == "mistral:latest"


def test_ollama_tool_schema_uses_mcp_input_schema() -> None:
    tool = SimpleNamespace(
        name="get_account",
        description="Return an account",
        inputSchema={"type": "object", "properties": {"account_id": {"type": "integer"}}},
    )

    assert _tool_schema(tool) == {
        "type": "function",
        "function": {
            "name": "get_account",
            "description": "Return an account",
            "parameters": tool.inputSchema,
        },
    }


def test_ollama_messages_and_tool_calls_are_serializable() -> None:
    message = SimpleNamespace(
        model_dump=lambda **_: {"role": "assistant", "content": "hello"}
    )
    tool_call = SimpleNamespace(
        model_dump=lambda **_: {
            "function": {"name": "get_account", "arguments": {"account_id": 1}}
        }
    )

    assert _message_dict(message)["role"] == "assistant"
    assert _tool_call_dict(tool_call)["function"]["name"] == "get_account"


def test_textual_tool_calls_only_accept_registered_json_tools() -> None:
    calls = _textual_tool_calls(
        '[{"name":"get_account","arguments":{"account_id":1}}]',
        {"get_account"},
    )
    assert calls[0]["function"]["name"] == "get_account"
    assert _textual_tool_calls(
        '[{"name":"execute_sql","arguments":{"query":"DROP TABLE"}}]',
        {"get_account"},
    ) == []
    malformed_wrapper = '["function": {"name": "get_account", "arguments": {"account_id": 1}}]'
    assert _textual_tool_calls(malformed_wrapper, {"get_account"})[0]["function"]["name"] == "get_account"


def test_textual_tool_calls_accept_labeled_prose_tool_arguments() -> None:
    content = """To change the transaction amount, call the `update_transaction` function.

- `transaction_id`: 4495
- `transaction_amount`: 12222.22
"""

    assert _textual_tool_calls(content, {"update_transaction"}) == [
        {
            "function": {
                "name": "update_transaction",
                "arguments": {
                    "transaction_id": 4495,
                    "transaction_amount": 12222.22,
                },
            }
        }
    ]


def test_textual_tool_calls_accept_natural_language_write_response() -> None:
    content = """To change the transaction amount of transaction ID 4495, first secure
the admin email and password. Then, call the `update_transaction` tool with the
supplied transaction ID and the new transaction amount.

After executing the above, the transaction amount for transaction ID 4495 should
be 12222.22"""

    assert _textual_tool_calls(content, {"update_transaction"}) == [
        {
            "function": {
                "name": "update_transaction",
                "arguments": {
                    "transaction_id": 4495,
                    "transaction_amount": 12222.22,
                },
            }
        }
    ]


def test_textual_tool_calls_ignore_placeholder_credentials_in_pseudo_call() -> None:
    content = """Here's the call with the provided data:

update_transaction(transaction_id=4495, transaction_amount=12222.22,
account_id=75, email=<USER_EMAIL>, password=<USER_PASSWORD>)"""

    assert _textual_tool_calls(content, {"update_transaction"}) == [
        {
            "function": {
                "name": "update_transaction",
                "arguments": {
                    "transaction_id": 4495,
                    "transaction_amount": 12222.22,
                    "account_id": 75,
                },
            }
        }
    ]


def test_textual_tool_calls_accept_literal_python_style_calls() -> None:
    calls = _textual_tool_calls(
        'get_customer(name="Priyal Shah")',
        {"get_customer"},
    )

    assert calls == [
        {
            "function": {
                "name": "get_customer",
                "arguments": {"name": "Priyal Shah"},
            }
        }
    ]


def test_textual_tool_calls_ignore_attribute_calls_without_crashing() -> None:
    assert _textual_tool_calls(
        'tools.get_customer(name="Priyal Shah")',
        {"get_customer"},
    ) == [
        {
            "function": {
                "name": "get_customer",
                "arguments": {"name": "Priyal Shah"},
            }
        }
    ]


def test_account_lookup_requires_explicit_account_id() -> None:
    assert _has_explicit_account_id("balance in account 23")
    assert not _has_explicit_account_id("balance in Sneha Verma's account")
    assert _requires_customer_resolution("balance in Sneha Verma's account", "get_account")
    assert not _requires_customer_resolution("balance in account 23", "get_account")


def test_account_balance_request_extracts_account_id() -> None:
    assert _account_id_for_balance("What is the balance in account 1?") == 1
    assert _account_id_for_balance("Show account number 23 balance") == 23
    assert _account_id_for_balance("What is the balance for Aarav Gupta?") is None


def test_unexecuted_balance_workflow_is_not_a_final_answer() -> None:
    assert _looks_like_unexecuted_plan(
        """```python
for customer in customers:
    account_summary = get_account_summary(customer_id=customer[\"customer_id\"])
return f\"Total balance: ${total_balance}\"```"""
    )
    assert not _looks_like_unexecuted_plan("Total balance for Manav Mehta: $100.00")


def test_customer_name_is_extracted_from_total_balance_question() -> None:
    assert _customer_name_for_total_balance(
        "What is the total balance in Manav Mehta total account balance?"
    ) == "Manav Mehta"
    assert _customer_name_for_total_balance(
        "What is Kabir Nair total bank Banlance?"
    ) == "Kabir Nair"
    assert _customer_name_for_total_balance(
        "What is Priya total account balance?"
    ) == "Priya"
    assert _customer_name_for_total_balance(
        "What is Mary Jane Watson total balance?"
    ) == "Mary Jane Watson"
    assert _customer_name_for_total_balance("What is the balance in account 8?") is None


def test_customer_name_is_extracted_from_total_savings_question() -> None:
    assert _customer_name_for_total_savings(
        "Tell me the total savings in Vivaan Rao's account?"
    ) == "Vivaan Rao"


def test_customer_name_is_extracted_from_details_question() -> None:
    assert _customer_name_for_details("Get customer details of Aarav Gupta") == (
        "Aarav Gupta"
    )
    assert _customer_name_for_details("Get customer information for Priya Shah?") == (
        "Priya Shah"
    )


def test_transaction_amount_update_request_is_parsed() -> None:
    assert _transaction_amount_update_request(
        "Change the transaction amount of Transaction_id 13 to 6100.98"
    ) == (13, Decimal("6100.98"))


def test_transaction_summary_request_accepts_arbitrary_dates_and_type() -> None:
    assert _transaction_summary_request(
        "What is the total transaction amount from 2025-01-25 to 2025-09-29?"
    ) == ("2025-01-25", "2025-09-29", None)
    assert _transaction_summary_request(
        "How many debit transactions were made from 2024-02-01 to 2026-11-30?"
    ) == ("2024-02-01", "2026-11-30", "Debit")
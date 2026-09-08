from types import SimpleNamespace

from llm.ollama_agent import (
    DEFAULT_MODEL,
    _message_dict,
    _tool_call_dict,
    _tool_schema,
    _textual_tool_calls,
    _has_explicit_account_id,
    _requires_customer_resolution,
)


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


def test_account_lookup_requires_explicit_account_id() -> None:
    assert _has_explicit_account_id("balance in account 23")
    assert not _has_explicit_account_id("balance in Sneha Verma's account")
    assert _requires_customer_resolution("balance in Sneha Verma's account", "get_account")
    assert not _requires_customer_resolution("balance in account 23", "get_account")
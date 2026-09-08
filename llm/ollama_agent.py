import asyncio
import json
import os
import re
from contextlib import AsyncExitStack
from typing import Any

from ollama import AsyncClient, ResponseError

from clients.dual_client import call_tool, connect_to_server


DEFAULT_MODEL = "mistral:latest"
MAX_TOOL_ROUNDS = 5

SYSTEM_PROMPT = """You are a banking assistant.

Use the available MCP tools for banking data. Never invent customer, account,
or transaction facts. Read tools are safe to use. Write tools change banking
data and require the user's explicit intent; never delete a transaction unless
the user clearly confirms the exact deletion request. Explain errors clearly.
Money values returned by tools are decimal strings; preserve their precision.
For any question about customers, accounts, or transactions, you MUST call the
appropriate MCP tool before answering. Do not return Python, JavaScript, or
pseudo-code showing how a tool could be called; execute the tool instead.
Never invent an account ID or customer ID. If the user provides a customer
name but no account ID, call get_customer with the name first, then call
get_customer_accounts for each matching customer. Ask for clarification when
multiple customers match.
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


async def ask_banking(
    prompt: str,
    *,
    model: str | None = None,
    max_tool_rounds: int = MAX_TOOL_ROUNDS,
    ollama_client: AsyncClient | None = None,
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
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Use an MCP tool to answer this banking request. Return a "
                    "tool call, not code or instructions. Request: " + prompt
                ),
            },
        ]

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
                                "You did not call an MCP tool. This is a banking "
                                "data question. Call the appropriate tool now; "
                                "do not provide code or an unverified answer."
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
                session = routing.get(name)
                if _requires_customer_resolution(prompt, name):
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
                        result = await call_tool(session, name, arguments)
                        tool_result = result
                    except RuntimeError as error:
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
import asyncio
import os
import sys
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def server_parameters(module_name: str) -> StdioServerParameters:
    environment = os.environ.copy()
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", module_name],
        env=environment,
        cwd=PROJECT_ROOT,
    )


@asynccontextmanager
async def connect_to_server(module_name: str) -> AsyncIterator[ClientSession]:
    parameters = server_parameters(module_name)
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            yield session


async def discover_tools(session: ClientSession) -> list[str]:
    response = await session.list_tools()
    return [tool.name for tool in response.tools]


async def call_tool(
    session: ClientSession, name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    result = await session.call_tool(name, arguments)
    if result.isError:
        error_text = [
            content.text
            for content in result.content
            if hasattr(content, "text")
        ]
        raise RuntimeError("; ".join(error_text) or f"MCP tool failed: {name}")
    return result.structuredContent or {}


async def run_demo() -> dict[str, Any]:
    async with AsyncExitStack() as stack:
        read_session = await stack.enter_async_context(
            connect_to_server("servers.read_server")
        )
        write_session = await stack.enter_async_context(
            connect_to_server("servers.write_server")
        )
        return {
            "read_tools": await discover_tools(read_session),
            "write_tools": await discover_tools(write_session),
            "account_summary": await call_tool(
                read_session, "get_account_summary", {"account_id": 1}
            ),
        }


def main() -> None:
    result = asyncio.run(run_demo())
    print(f"Read tools: {', '.join(result['read_tools'])}")
    print(f"Write tools: {', '.join(result['write_tools'])}")
    print(f"Account 1 summary: {result['account_summary']}")


if __name__ == "__main__":
    main()
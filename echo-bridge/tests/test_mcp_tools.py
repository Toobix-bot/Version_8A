from __future__ import annotations

import asyncio
from typing import Any

from fastmcp import Client

from echo_bridge.mcp_fastmcp import mcp
from echo_bridge.main import settings
from echo_bridge.db import init_db
from echo_bridge.services.memory_service import add_chunks


async def _run_async_test() -> None:
    # Ensure database is initialized and has a record
    init_db(settings.db_path)
    add_chunks("test", "hello", ["FastMCP test record"], None)

    # Connect to the in-memory MCP server instance
    async with Client(mcp) as client:
        tools = await client.list_tools()
        assert any(t.name == "memory_search" for t in tools)

        # Call memory_search tool
        result = await client.call_tool("memory_search", {"query": "test", "k": 3})
        # Content is a list of messages; FastMCP flattens JSON results
        # into message content; we assert we received some content back
        assert result.content, "Empty MCP response"


def test_mcp_memory_search_smoke() -> None:
    asyncio.run(_run_async_test())

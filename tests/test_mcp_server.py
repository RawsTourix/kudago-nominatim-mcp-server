import pytest
from fastmcp import Client

from app.mcp.server import mcp


@pytest.mark.asyncio
async def test_resolve_place_tool_is_registered():
    async with Client(mcp) as client:
        tools = await client.list_tools()

    assert "resolve_place" in {tool.name for tool in tools}

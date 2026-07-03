import pytest
from fastmcp import Client

from app.mcp.server import mcp


@pytest.mark.asyncio
async def test_first_application_tools_are_registered():
    async with Client(mcp) as client:
        tools = await client.list_tools()

    assert {"events", "resolve_place"} <= {tool.name for tool in tools}

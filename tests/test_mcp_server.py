import pytest
from fastmcp import Client

from app.mcp.server import mcp


@pytest.mark.asyncio
async def test_first_application_tools_are_registered():
    async with Client(mcp) as client:
        tools = await client.list_tools()

    assert {"events", "places", "resolve_place"} <= {
        tool.name for tool in tools
    }


@pytest.mark.asyncio
async def test_places_tool_rejects_partial_coordinates_before_creating_job():
    async with Client(mcp) as client:
        result = await client.call_tool("places", {"lat": 55.75})

    assert result.data["status"] == "error"
    assert result.data["tool"] == "places"
    assert result.data["job_id"] is None
    assert result.data["error_type"] == "ValidationError"

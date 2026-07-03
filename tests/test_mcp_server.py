import pytest
from fastmcp import Client

from app.mcp.server import mcp


@pytest.mark.asyncio
async def test_first_application_tools_are_registered():
    async with Client(mcp) as client:
        tools = await client.list_tools()

    assert {
        "events",
        "lists",
        "movie_showings",
        "movies",
        "news",
        "object",
        "places",
        "reference",
        "resolve_place",
    } <= {
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


@pytest.mark.asyncio
async def test_reference_tool_rejects_location_without_slug():
    async with Client(mcp) as client:
        result = await client.call_tool("reference", {"kind": "location"})

    assert result.data["status"] == "error"
    assert result.data["tool"] == "reference"
    assert result.data["job_id"] is None
    assert result.data["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_movie_showings_tool_rejects_partial_time_window():
    async with Client(mcp) as client:
        result = await client.call_tool(
            "movie_showings",
            {"location": "msk", "actual_since": 1_700_000_000},
        )

    assert result.data["status"] == "error"
    assert result.data["tool"] == "movie_showings"
    assert result.data["job_id"] is None
    assert result.data["error_type"] == "ValidationError"

import pytest
from fastmcp import Client

from app.mcp.server import mcp


@pytest.mark.asyncio
async def test_first_application_tools_are_registered():
    async with Client(mcp) as client:
        tools = await client.list_tools()

    tools_by_name = {tool.name: tool for tool in tools}
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
        "street_route",
        "transit_route",
    } <= set(tools_by_name)
    assert "Use movie_showings" in tools_by_name["places"].description
    assert "actual cinema showings" in tools_by_name["movie_showings"].description
    reference_tool = tools_by_name["reference"]
    assert "not a complete" in reference_tool.description
    assert reference_tool.inputSchema["properties"]["kind"]["enum"] == [
        "event_categories",
        "place_categories",
        "locations",
        "location",
    ]
    assert "Do not invent" in tools_by_name["transit_route"].description
    assert "Do not infer public transport" in tools_by_name["street_route"].description
    transit_schema = str(tools_by_name["transit_route"].inputSchema)
    street_schema = str(tools_by_name["street_route"].inputSchema)
    assert "SUBURBAN" in transit_schema
    assert "AERIAL_LIFT" in transit_schema
    assert "walking" in street_schema
    assert "cycling" in street_schema
    assert "driving" in street_schema


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


@pytest.mark.asyncio
async def test_transit_route_rejects_identical_points_before_creating_job():
    async with Client(mcp) as client:
        result = await client.call_tool(
            "transit_route",
            {
                "origin_lat": 55.75,
                "origin_lon": 37.61,
                "destination_lat": 55.75,
                "destination_lon": 37.61,
            },
        )

    assert result.data["status"] == "error"
    assert result.data["tool"] == "transit_route"
    assert result.data["job_id"] is None
    assert result.data["error_type"] == "ValidationError"

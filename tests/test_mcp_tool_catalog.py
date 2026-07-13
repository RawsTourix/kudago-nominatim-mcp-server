from types import SimpleNamespace

import pytest
from fastmcp import Client

from app.mcp.server import create_mcp_server


EXPECTED_TOOLS = {
    "resolve_location",
    "find_events",
    "find_places",
    "find_movies",
    "find_movie_showings",
    "find_city_news",
    "find_city_guides",
    "get_details",
    "plan_public_transport",
    "plan_street_route",
}
OLD_TOOLS = {
    "resolve_place",
    "events",
    "places",
    "movies",
    "movie_showings",
    "news",
    "lists",
    "reference",
    "object",
    "transit_route",
    "street_route",
}


@pytest.mark.asyncio
async def test_fully_configured_catalog_contains_exactly_ten_agent_tools():
    server = create_mcp_server(
        settings_obj=SimpleNamespace(
            transitous_user_agent="tests/1.0 tests@example.com",
            openrouteservice_api_key="test-key",
        )
    )
    async with Client(server) as client:
        tools = await client.list_tools()

    names = {tool.name for tool in tools}
    assert names == EXPECTED_TOOLS
    assert names.isdisjoint(OLD_TOOLS)
    for tool in tools:
        assert tool.description
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
        assert tool.annotations.idempotentHint is True
        assert tool.annotations.openWorldHint is True

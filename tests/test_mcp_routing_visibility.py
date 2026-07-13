from types import SimpleNamespace

import pytest
from fastmcp import Client

from app.mcp.server import create_mcp_server


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("transit_user_agent", "ors_key", "present", "absent"),
    [
        (None, "key", "plan_street_route", "plan_public_transport"),
        ("tests/1.0 tests@example.com", None, "plan_public_transport", "plan_street_route"),
    ],
)
async def test_unconfigured_routing_provider_is_not_published(
    transit_user_agent,
    ors_key,
    present,
    absent,
):
    server = create_mcp_server(
        settings_obj=SimpleNamespace(
            transitous_user_agent=transit_user_agent,
            openrouteservice_api_key=ors_key,
        )
    )
    async with Client(server) as client:
        names = {tool.name for tool in await client.list_tools()}

    assert present in names
    assert absent not in names

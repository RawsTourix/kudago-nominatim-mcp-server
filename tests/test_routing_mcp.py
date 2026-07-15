from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastmcp import Client

from app.mcp.server import create_mcp_server
from app.mcp.tools import routing


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "command", "extra_args"),
    [
        (
            "plan_public_transport",
            "routing.transit.plan",
            {"departure_time": "2026-07-15T18:00:00+03:00"},
        ),
        (
            "plan_street_route",
            "routing.street.plan",
            {"travel_mode": "cycling"},
        ),
    ],
)
async def test_routing_tools_use_shared_mcp_executor(
    monkeypatch,
    fake_mcp_redis,
    tool_name,
    command,
    extra_args,
):
    run = AsyncMock(
        return_value={
            "status": "ok",
            "tool": tool_name,
            "job_id": "job-id",
            "data": {"routes": []},
        }
    )
    monkeypatch.setattr(routing, "run_mcp_command", run)
    server = create_mcp_server(
        settings_obj=SimpleNamespace(
            redis_url="redis://test:6379/0",
            mcp_job_wait_timeout_seconds=180.0,
            transitous_user_agent="tests/1.0 tests@example.com",
            openrouteservice_api_key="test-key",
        )
    )
    arguments = {
        "origin": {
            "latitude": 55.842,
            "longitude": 37.180,
            "label": "Origin",
        },
        "destination": {
            "latitude": 55.751,
            "longitude": 37.617,
            "label": "Destination",
        },
        **extra_args,
    }

    async with Client(server) as client:
        result = await client.call_tool(tool_name, arguments)

    assert result.data["status"] == "ok"
    kwargs = run.await_args.kwargs
    assert kwargs["redis"] is fake_mcp_redis.redis
    assert kwargs["command"] == command
    assert kwargs["endpoint"] == f"mcp://tools/{tool_name}"
    assert kwargs["request_text"] == "55.842,37.18 -> 55.751,37.617"
    assert kwargs["payload"]["origin_lat"] == 55.842
    assert kwargs["data_factory"].keywords["agent_request"].origin.label == "Origin"
    if tool_name == "plan_street_route":
        assert kwargs["payload"]["profile"] == "cycling"
        assert kwargs["payload"]["include_geometry"] is False
    else:
        assert kwargs["payload"]["transit_modes"] == ["TRANSIT"]
        assert kwargs["payload"]["num_itineraries"] == 3

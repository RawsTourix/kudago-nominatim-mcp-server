from types import SimpleNamespace

import pytest
from fastmcp import Client

from app.mcp.server import create_mcp_server


def fully_configured_server():
    return create_mcp_server(
        settings_obj=SimpleNamespace(
            transitous_user_agent="tests/1.0 tests@example.com",
            openrouteservice_api_key="test-key",
        )
    )


@pytest.mark.asyncio
async def test_cross_field_validation_returns_agent_error_before_job_creation():
    async with Client(fully_configured_server()) as client:
        result = await client.call_tool(
            "find_events",
            {
                "coordinates": {"latitude": 55.75, "longitude": 37.61},
                "date": "2026-07-13",
            },
        )

    assert result.data["status"] == "error"
    assert result.data["tool"] == "find_events"
    assert result.data["job_id"] is None
    assert result.data["error_type"] == "validation_error"
    assert result.data["retryable"] is True
    assert result.data["details"]


@pytest.mark.asyncio
async def test_routing_rejects_identical_points_before_job_creation():
    point = {"latitude": 55.75, "longitude": 37.61}
    async with Client(fully_configured_server()) as client:
        result = await client.call_tool(
            "plan_public_transport",
            {"origin": point, "destination": point},
        )

    assert result.data["status"] == "error"
    assert result.data["tool"] == "plan_public_transport"
    assert result.data["job_id"] is None
    assert result.data["error_type"] == "validation_error"

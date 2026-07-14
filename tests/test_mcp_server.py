from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastmcp import Client

from app.mcp.server import create_mcp_server
from app.mcp.tools import discovery


def fully_configured_server():
    return create_mcp_server(
        settings_obj=SimpleNamespace(
            redis_url="redis://test:6379/0",
            mcp_job_wait_timeout_seconds=23.5,
            transitous_user_agent="tests/1.0 tests@example.com",
            openrouteservice_api_key="test-key",
        )
    )


@pytest.mark.asyncio
async def test_cross_field_validation_returns_agent_error_before_job_creation(
    fake_mcp_redis,
):
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
async def test_routing_rejects_identical_points_before_job_creation(fake_mcp_redis):
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


@pytest.mark.asyncio
async def test_find_events_maps_ekb_calendar_date_with_snapshot_timezone(
    monkeypatch,
    fake_mcp_redis,
):
    run = AsyncMock(
        return_value={
            "status": "ok",
            "tool": "find_events",
            "job_id": "job-id",
            "data": {"items": []},
        }
    )
    monkeypatch.setattr(discovery, "run_mcp_command", run)

    async with Client(fully_configured_server()) as client:
        result = await client.call_tool(
            "find_events",
            {"location_slug": "ekb", "date": "2026-07-14"},
        )

    assert result.data["status"] == "ok"
    kwargs = run.await_args.kwargs
    assert kwargs["redis"] is fake_mcp_redis.redis
    assert kwargs["wait_timeout_seconds"] == 23.5
    assert kwargs["payload"]["actual_since"] == 1783969200
    assert kwargs["payload"]["actual_until"] == 1784055599
    assert kwargs["data_factory"].keywords["applied_timezone"] == (
        "Asia/Yekaterinburg"
    )
    assert kwargs["data_factory"].keywords["applied_filters"]["timezone"] == (
        "Asia/Yekaterinburg"
    )


@pytest.mark.asyncio
async def test_mcp_lifespan_opens_and_closes_one_configured_redis_pool(
    fake_mcp_redis,
):
    async with Client(fully_configured_server()) as client:
        await client.list_tools()

    fake_mcp_redis.create_pool.assert_awaited_once_with("redis://test:6379/0")
    fake_mcp_redis.close_pool.assert_awaited_once_with(fake_mcp_redis.redis)

from unittest.mock import AsyncMock

import pytest
from fastmcp import Client

from app.mcp.server import mcp
from app.mcp.tools import routing


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "command", "extra_args"),
    [
        ("transit_route", "routing.transit.plan", {}),
        ("street_route", "routing.street.plan", {"profile": "cycling"}),
    ],
)
async def test_routing_tools_use_shared_mcp_executor(
    monkeypatch,
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
    arguments = {
        "origin_lat": 55.842,
        "origin_lon": 37.180,
        "destination_lat": 55.751,
        "destination_lon": 37.617,
        **extra_args,
    }

    async with Client(mcp) as client:
        result = await client.call_tool(tool_name, arguments)

    assert result.data["status"] == "ok"
    kwargs = run.await_args.kwargs
    assert kwargs["command"] == command
    assert kwargs["endpoint"] == f"mcp://tools/{tool_name}"
    assert kwargs["request_text"] == "55.842,37.18 -> 55.751,37.617"
    assert kwargs["payload"]["origin_lat"] == 55.842

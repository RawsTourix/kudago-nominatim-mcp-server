import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.application.contracts import CommandOutput
from app.mcp import executor


class _SessionContext:
    def __init__(self) -> None:
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None


@pytest.mark.asyncio
async def test_mcp_serialization_failure_logs_traceback_but_returns_safe_error(
    monkeypatch,
    caplog,
):
    session = _SessionContext()
    job = SimpleNamespace(id="job-id")
    output = CommandOutput(
        status="ok",
        result_type="events.search",
        items=[],
        meta={},
        result_payload={"status": "ok", "items": []},
    )
    job_service = SimpleNamespace(
        create_job_from_request=AsyncMock(return_value=job)
    )
    command_executor = SimpleNamespace(
        run_payload=AsyncMock(return_value=output)
    )

    monkeypatch.setattr(executor, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(executor, "JobService", lambda _: job_service)
    monkeypatch.setattr(executor, "CommandExecutor", lambda _: command_executor)

    def fail_serialization(_output):
        raise OSError("sentinel timestamp is outside the platform range")

    with caplog.at_level(logging.ERROR, logger="app.mcp.executor"):
        result = await executor.run_mcp_command(
            tool_name="find_events",
            endpoint="/mcp/tools/find_events",
            command="events.search",
            payload={"location": "msk"},
            data_factory=fail_serialization,
        )

    assert result["status"] == "error"
    assert result["message"] == (
        "The complete result was saved, but MCP serialization failed."
    )
    assert result["error_type"] == "OSError"
    assert result["retryable"] is False
    assert "traceback" not in result
    assert "sentinel timestamp" not in result["message"]
    assert (
        "MCP serialization failed: tool=find_events job_id=job-id "
        "command=events.search"
    ) in caplog.text
    assert "Traceback" in caplog.text
    assert "sentinel timestamp is outside the platform range" in caplog.text

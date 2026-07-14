import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.application.contracts import CommandOutput
from app.mcp import executor


class _SessionContext:
    def __init__(self, name: str, events: list[str]) -> None:
        self.name = name
        self.events = events
        self.active = False

    async def __aenter__(self):
        self.active = True
        self.events.append(f"{self.name}:enter")
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        self.active = False
        self.events.append(f"{self.name}:exit")
        return None


def _output() -> CommandOutput:
    return CommandOutput(
        status="ok",
        result_type="events.search",
        items=[{"id": 1}],
        meta={"source": "worker"},
        result_payload={"status": "ok", "items": [{"id": 1}]},
    )


def _install_success_path(monkeypatch, *, result_side_effect=None):
    events: list[str] = []
    sessions = [
        _SessionContext("dispatch", events),
        _SessionContext("load", events),
    ]
    job = SimpleNamespace(id=uuid4())

    async def wait_for_result(*, timeout):
        assert all(not session.active for session in sessions)
        events.append(f"wait:{timeout}")
        if result_side_effect is not None:
            raise result_side_effect
        return {"status": "ok", "job_id": str(job.id)}

    arq_job = SimpleNamespace(
        job_id=f"events.search:{job.id}",
        result=AsyncMock(side_effect=wait_for_result),
        abort=AsyncMock(),
    )
    dispatched = SimpleNamespace(job=job, arq_job=arq_job)
    dispatch_service = SimpleNamespace(
        create_and_enqueue=AsyncMock(return_value=dispatched)
    )
    command_executor = SimpleNamespace(
        load_completed_output=AsyncMock(return_value=_output()),
        run_payload=AsyncMock(),
    )

    monkeypatch.setattr(executor, "AsyncSessionLocal", lambda: sessions.pop(0))
    monkeypatch.setattr(
        executor,
        "JobDispatchService",
        lambda session, redis: dispatch_service,
    )
    monkeypatch.setattr(executor, "CommandExecutor", lambda session: command_executor)
    return SimpleNamespace(
        events=events,
        job=job,
        arq_job=arq_job,
        dispatch_service=dispatch_service,
        command_executor=command_executor,
    )


@pytest.mark.asyncio
async def test_mcp_queues_waits_without_open_session_and_loads_persisted_output(
    monkeypatch,
):
    state = _install_success_path(monkeypatch)
    serializer = Mock(return_value={"items": [{"id": 1}]})
    redis = SimpleNamespace()

    result = await executor.run_mcp_command(
        redis=redis,
        wait_timeout_seconds=17.5,
        tool_name="find_events",
        endpoint="mcp://tools/find_events",
        command="events.search",
        payload={"location": "msk"},
        data_factory=serializer,
    )

    assert result["status"] == "ok"
    assert result["job_id"] == str(state.job.id)
    state.dispatch_service.create_and_enqueue.assert_awaited_once_with(
        endpoint="mcp://tools/find_events",
        method="MCP",
        command="events.search",
        input_payload={"location": "msk"},
        request_text=None,
    )
    state.arq_job.result.assert_awaited_once_with(
        timeout=17.5
    )
    state.command_executor.load_completed_output.assert_awaited_once_with(
        state.job.id
    )
    state.command_executor.run_payload.assert_not_awaited()
    serializer.assert_called_once_with(_output())
    assert state.events == [
        "dispatch:enter",
        "dispatch:exit",
        "wait:17.5",
        "load:enter",
        "load:exit",
    ]


@pytest.mark.asyncio
async def test_mcp_timeout_returns_non_retryable_error_without_aborting_job(
    monkeypatch,
):
    events: list[str] = []
    sessions = [
        _SessionContext("dispatch", events),
        _SessionContext("pending-job", events),
    ]
    job = SimpleNamespace(id=uuid4())
    arq_job = SimpleNamespace(
        job_id=f"events.search:{job.id}",
        result=AsyncMock(side_effect=TimeoutError),
        abort=AsyncMock(),
    )
    dispatch_service = SimpleNamespace(
        create_and_enqueue=AsyncMock(
            return_value=SimpleNamespace(job=job, arq_job=arq_job)
        )
    )
    job_service = SimpleNamespace(
        get_by_id=AsyncMock(
            return_value=SimpleNamespace(id=job.id, status="running")
        )
    )
    monkeypatch.setattr(executor, "AsyncSessionLocal", lambda: sessions.pop(0))
    monkeypatch.setattr(
        executor,
        "JobDispatchService",
        lambda session, redis: dispatch_service,
    )
    monkeypatch.setattr(executor, "JobService", lambda session: job_service)

    result = await executor.run_mcp_command(
        redis=SimpleNamespace(),
        wait_timeout_seconds=17.5,
        tool_name="find_events",
        endpoint="mcp://tools/find_events",
        command="events.search",
        payload={},
    )

    assert result == {
        "status": "error",
        "tool": "find_events",
        "job_id": str(job.id),
        "message": (
            "The job is still queued or running and did not finish within "
            "the MCP wait timeout."
        ),
        "error_type": "processing_timeout",
        "retryable": False,
    }
    arq_job.abort.assert_not_awaited()
    job_service.get_by_id.assert_awaited_once_with(job.id)


@pytest.mark.asyncio
async def test_mcp_worker_error_uses_failed_job_diagnostics(monkeypatch):
    events: list[str] = []
    sessions = [
        _SessionContext("dispatch", events),
        _SessionContext("failed-job", events),
    ]
    job = SimpleNamespace(id=uuid4())
    arq_job = SimpleNamespace(
        result=AsyncMock(side_effect=RuntimeError("worker transport detail")),
    )
    dispatch_service = SimpleNamespace(
        create_and_enqueue=AsyncMock(
            return_value=SimpleNamespace(job=job, arq_job=arq_job)
        )
    )
    failed_job = SimpleNamespace(
        id=job.id,
        status="failed",
        error_type="UpstreamError",
        error_message="The upstream request failed.",
    )
    job_service = SimpleNamespace(get_by_id=AsyncMock(return_value=failed_job))
    monkeypatch.setattr(executor, "AsyncSessionLocal", lambda: sessions.pop(0))
    monkeypatch.setattr(
        executor,
        "JobDispatchService",
        lambda session, redis: dispatch_service,
    )
    monkeypatch.setattr(executor, "JobService", lambda session: job_service)

    result = await executor.run_mcp_command(
        redis=SimpleNamespace(),
        wait_timeout_seconds=17.5,
        tool_name="find_events",
        endpoint="mcp://tools/find_events",
        command="events.search",
        payload={},
    )

    assert result["error_type"] == "UpstreamError"
    assert result["message"] == "The upstream request failed."
    assert result["retryable"] is False
    job_service.get_by_id.assert_awaited_once_with(job.id)


@pytest.mark.asyncio
async def test_mcp_cancellation_propagates_without_aborting_worker_job(monkeypatch):
    events: list[str] = []
    session = _SessionContext("dispatch", events)
    job = SimpleNamespace(id=uuid4())
    arq_job = SimpleNamespace(
        result=AsyncMock(side_effect=asyncio.CancelledError),
        abort=AsyncMock(),
    )
    dispatch_service = SimpleNamespace(
        create_and_enqueue=AsyncMock(
            return_value=SimpleNamespace(job=job, arq_job=arq_job)
        )
    )
    monkeypatch.setattr(executor, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(
        executor,
        "JobDispatchService",
        lambda session, redis: dispatch_service,
    )

    with pytest.raises(asyncio.CancelledError):
        await executor.run_mcp_command(
            redis=SimpleNamespace(),
            wait_timeout_seconds=17.5,
            tool_name="find_events",
            endpoint="mcp://tools/find_events",
            command="events.search",
            payload={},
        )

    arq_job.abort.assert_not_awaited()


@pytest.mark.asyncio
async def test_mcp_serialization_failure_logs_traceback_but_returns_safe_error(
    monkeypatch,
    caplog,
):
    state = _install_success_path(monkeypatch)

    def fail_serialization(_output):
        raise OSError("sentinel timestamp is outside the platform range")

    with caplog.at_level(logging.ERROR, logger="app.mcp.executor"):
        result = await executor.run_mcp_command(
            redis=SimpleNamespace(),
            wait_timeout_seconds=17.5,
            tool_name="find_events",
            endpoint="mcp://tools/find_events",
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
        f"MCP serialization failed: tool=find_events job_id={state.job.id} "
        "command=events.search"
    ) in caplog.text
    assert "Traceback" in caplog.text
    assert "sentinel timestamp is outside the platform range" in caplog.text

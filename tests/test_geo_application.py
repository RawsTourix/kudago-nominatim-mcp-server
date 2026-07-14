from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.contracts import CommandEvent, CommandOutput, ExecutionContext
from app.application.executor import CommandExecutor
from app.application.handlers.geo import GeoResolveHandler


@pytest.mark.asyncio
async def test_geo_handler_builds_transport_neutral_output():
    job_id = uuid4()
    handler = GeoResolveHandler.__new__(GeoResolveHandler)
    handler.geo_service = SimpleNamespace(
        resolve_place=AsyncMock(
            return_value={
                "status": "ambiguous",
                "source": "nominatim",
                "query": "Springfield",
                "candidates": [{"lat": "1", "lon": "2"}],
                "selected_lat": None,
                "selected_lon": None,
                "radius": None,
            }
        )
    )

    output = await handler.run(
        ExecutionContext(
            job_id=job_id,
            command="geo.resolve",
            source="test",
        ),
        {"query": "Springfield", "limit": 5},
    )

    assert output.status == "ambiguous"
    assert output.result_type == "geo.resolve"
    assert output.items == [{"lat": "1", "lon": "2"}]
    assert output.meta["source"] == "nominatim"
    handler.geo_service.resolve_place.assert_awaited_once_with(
        job_id=job_id,
        query="Springfield",
        countrycodes="ru",
        limit=5,
        accept_language="ru",
    )


@pytest.mark.asyncio
async def test_executor_persists_success_lifecycle():
    job = SimpleNamespace(
        id=uuid4(),
        command="geo.resolve",
        status="queued",
        input_payload={"query": "Moscow"},
        result_payload=None,
    )
    output = CommandOutput(
        status="ok",
        result_type="geo.resolve",
        items=[{"lat": "55.75", "lon": "37.62"}],
        meta={"status": "ok"},
        result_payload={"status": "ok", "candidates": []},
        events=[
            CommandEvent(
                event_type="custom",
                message="Custom handler event",
                data={"value": 1},
            )
        ],
    )
    executor = CommandExecutor(SimpleNamespace())
    executor.job_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=job),
        mark_running=AsyncMock(),
        mark_succeeded=AsyncMock(),
        mark_failed=AsyncMock(),
        add_event=AsyncMock(),
    )
    executor.result_repo = SimpleNamespace(create=AsyncMock())
    executor._dispatch = AsyncMock(return_value=output)

    actual = await executor.run_payload(
        job_id=job.id,
        command=job.command,
        payload=job.input_payload,
        source="test",
    )

    assert actual is output
    executor.job_repo.mark_running.assert_awaited_once_with(job)
    executor.result_repo.create.assert_awaited_once_with(
        job_id=job.id,
        result_type="geo.resolve",
        items=output.items,
        meta=output.meta,
    )
    executor.job_repo.mark_succeeded.assert_awaited_once_with(
        job,
        result_payload=output.result_payload,
    )
    assert executor.job_repo.add_event.await_count == 3
    executor.job_repo.add_event.assert_any_await(
        job_id=job.id,
        event_type="custom",
        message="Custom handler event",
        data={"value": 1},
    )


@pytest.mark.asyncio
async def test_executor_splits_started_state_from_handler_execution():
    job = SimpleNamespace(
        id=uuid4(),
        command="geo.resolve",
        status="queued",
        input_payload={"query": "Moscow"},
        result_payload=None,
    )
    output = CommandOutput(
        status="ok",
        result_type="geo.resolve",
        items=[],
        meta={},
        result_payload={"status": "ok", "candidates": []},
    )
    executor = CommandExecutor(SimpleNamespace())
    executor.job_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=job),
        mark_running=AsyncMock(),
        mark_succeeded=AsyncMock(),
        mark_failed=AsyncMock(),
        add_event=AsyncMock(),
    )
    executor.result_repo = SimpleNamespace(create=AsyncMock())
    executor._dispatch = AsyncMock(return_value=output)

    started = await executor.start_existing_job(job.id, source="worker")

    assert started is True
    executor.job_repo.mark_running.assert_awaited_once_with(job)
    executor.job_repo.add_event.assert_awaited_once_with(
        job_id=job.id,
        event_type="started",
        message="geo.resolve execution started",
        data={"command": "geo.resolve", "source": "worker"},
    )
    executor._dispatch.assert_not_awaited()

    job.status = "running"
    executor.job_repo.add_event.reset_mock()
    actual = await executor.execute_started_job(job.id, source="worker")

    assert actual is output
    executor.job_repo.mark_running.assert_awaited_once()
    executor._dispatch.assert_awaited_once()
    executor.job_repo.add_event.assert_awaited_once_with(
        job_id=job.id,
        event_type="completed",
        message="geo.resolve execution completed",
        data={
            "command": "geo.resolve",
            "source": "worker",
            "result_status": "ok",
        },
    )


@pytest.mark.asyncio
async def test_executor_persists_failure_lifecycle():
    job = SimpleNamespace(id=uuid4(), command="geo.resolve")
    executor = CommandExecutor(SimpleNamespace())
    executor.job_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=job),
        mark_running=AsyncMock(),
        mark_succeeded=AsyncMock(),
        mark_failed=AsyncMock(),
        add_event=AsyncMock(),
    )
    executor.result_repo = SimpleNamespace(create=AsyncMock())
    executor._dispatch = AsyncMock(side_effect=RuntimeError("Nominatim unavailable"))

    with pytest.raises(RuntimeError, match="Nominatim unavailable"):
        await executor.run_payload(
            job_id=job.id,
            command=job.command,
            payload={"query": "Moscow"},
            source="test",
        )

    executor.job_repo.mark_failed.assert_awaited_once_with(
        job,
        error_type="RuntimeError",
        error_message="Nominatim unavailable",
    )
    assert executor.job_repo.add_event.await_count == 2

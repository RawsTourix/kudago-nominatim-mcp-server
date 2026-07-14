import asyncio
import os
from contextlib import suppress
from uuid import UUID

import pytest
from arq.worker import Worker
from fastmcp import Client

from app.application.contracts import CommandOutput
from app.application.executor import HANDLERS
from app.core.config import settings
from app.core.db import AsyncSessionLocal, engine
from app.core.redis import create_arq_pool
from app.mcp.server import create_mcp_server
from app.repositories.job_repository import JobRepository
from app.repositories.result_repository import ResultRepository
from app.services.job_service import JobService
from app.workers.tasks import process_command_job


pytestmark = pytest.mark.skipif(
    os.getenv("KUDAGO_RUN_QUEUE_INTEGRATION") != "1",
    reason="set KUDAGO_RUN_QUEUE_INTEGRATION=1 with PostgreSQL and Redis available",
)


@pytest.fixture(autouse=True)
async def dispose_database_pool_after_test():
    yield
    await engine.dispose()


@pytest.mark.asyncio
async def test_mcp_command_runs_through_real_redis_worker_and_persists_once(
    monkeypatch,
):
    sources: list[str] = []

    class FakeGeoResolveHandler:
        command = "geo.resolve"

        def __init__(self, session):
            self.session = session

        async def run(self, context, payload):
            sources.append(context.source)
            candidate = {
                "display_name": "Integration City",
                "name": "Integration City",
                "type": "city",
                "lat": "55.75",
                "lon": "37.61",
            }
            return CommandOutput(
                status="ok",
                result_type="geo_candidates",
                items=[candidate],
                meta={"source": "mock_upstream", "items_count": 1},
                result_payload={
                    "status": "ok",
                    "source": "mock_upstream",
                    "query": payload["query"],
                    "candidates": [candidate],
                },
            )

    monkeypatch.setitem(HANDLERS, "geo.resolve", FakeGeoResolveHandler)
    worker_redis = await create_arq_pool(settings.redis_url)
    worker = Worker(
        [process_command_job],
        redis_pool=worker_redis,
        handle_signals=False,
        poll_delay=0.05,
        keep_result=3600,
    )
    worker_task = asyncio.create_task(worker.async_run())

    try:
        async with Client(create_mcp_server()) as client:
            result = await client.call_tool(
                "resolve_location",
                {"place": "Integration City", "limit": 1},
            )
    finally:
        await worker.close()
        with suppress(asyncio.CancelledError):
            await worker_task

    assert result.data["status"] == "ok"
    assert result.data["data"]["source"] == "mock_upstream"
    assert sources == ["worker"]

    job_id = UUID(result.data["job_id"])
    async with AsyncSessionLocal() as session:
        job = await JobService(session).get_by_id(job_id)
        events = await JobRepository(session).get_events(job_id)
        command_results = await ResultRepository(session).get_by_job_id(job_id)

    assert job is not None
    assert job.status == "succeeded"
    assert job.queue_job_id == f"geo.resolve:{job_id}"
    assert [event.event_type for event in events] == [
        "queued",
        "enqueued",
        "started",
        "completed",
    ]
    assert len(command_results) == 1

    await process_command_job({}, str(job_id))
    async with AsyncSessionLocal() as session:
        repeated_results = await ResultRepository(session).get_by_job_id(job_id)

    assert len(repeated_results) == 1
    assert sources == ["worker"]


@pytest.mark.asyncio
async def test_hanging_handler_fails_job_without_persisting_command_result(
    monkeypatch,
):
    class HangingGeoResolveHandler:
        command = "geo.resolve"

        def __init__(self, session):
            self.session = session

        async def run(self, context, payload):
            await asyncio.Event().wait()

    monkeypatch.setitem(HANDLERS, "geo.resolve", HangingGeoResolveHandler)
    monkeypatch.setattr(settings, "command_job_timeout_seconds", 0.05)
    worker_redis = await create_arq_pool(settings.redis_url)
    worker = Worker(
        [process_command_job],
        redis_pool=worker_redis,
        handle_signals=False,
        poll_delay=0.01,
        job_timeout=settings.arq_job_timeout_seconds,
        keep_result=3600,
    )
    worker_task = asyncio.create_task(worker.async_run())

    try:
        async with Client(create_mcp_server()) as client:
            result = await client.call_tool(
                "resolve_location",
                {"place": "Hanging Integration City", "limit": 1},
            )
    finally:
        await worker.close()
        with suppress(asyncio.CancelledError):
            await worker_task

    assert result.data["status"] == "error"
    assert result.data["error_type"] == "CommandTimeoutError"
    assert result.data["message"] == "Command execution exceeded its timeout."

    job_id = UUID(result.data["job_id"])
    async with AsyncSessionLocal() as session:
        job = await JobService(session).get_by_id(job_id)
        events = await JobRepository(session).get_events(job_id)
        command_results = await ResultRepository(session).get_by_job_id(job_id)

    assert job is not None
    assert job.status == "failed"
    assert job.error_type == "CommandTimeoutError"
    assert job.error_message == "Command execution exceeded its timeout."
    assert [event.event_type for event in events] == [
        "queued",
        "enqueued",
        "failed",
    ]
    assert events[-1].message == "Command execution timed out"
    assert events[-1].data == {"error_type": "CommandTimeoutError"}
    assert command_results == []

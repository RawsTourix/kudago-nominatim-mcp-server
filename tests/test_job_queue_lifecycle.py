from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.routers import (
    events,
    geo,
    lists,
    movie_showings,
    movies,
    news,
    places,
    routing,
)
from app.application.contracts import CommandOutput
from app.application.executor import CommandExecutor
from app.services import job_dispatch_service
from app.services.job_dispatch_service import JobDispatchService, JobEnqueueError
from app.services.queue_service import QueueService
from app.workers import tasks


class _SessionContext:
    def __init__(self) -> None:
        self.commit = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None


class _Payload(SimpleNamespace):
    def __init__(self, *, dumped: dict, **values):
        super().__init__(**values)
        self.dumped = dumped

    def model_dump(self, *args, **kwargs):
        return self.dumped


@pytest.mark.asyncio
async def test_queue_service_uses_generic_worker_and_deterministic_job_id():
    job_id = uuid4()
    arq_job = SimpleNamespace(job_id=f"events.search:{job_id}")
    redis = SimpleNamespace(enqueue_job=AsyncMock(return_value=arq_job))

    result = await QueueService(redis).enqueue_command_job(
        job_id=job_id,
        command="events.search",
    )

    assert result is arq_job
    redis.enqueue_job.assert_awaited_once_with(
        "process_command_job",
        str(job_id),
        _job_id=f"events.search:{job_id}",
    )


@pytest.mark.asyncio
async def test_dispatch_commits_job_before_enqueue_and_metadata_afterward(monkeypatch):
    calls: list[str] = []
    job = SimpleNamespace(id=uuid4(), command="events.search")
    arq_job = SimpleNamespace(job_id=f"events.search:{job.id}")

    async def create_job(**kwargs):
        calls.append("create")
        return job

    async def mark_enqueued(**kwargs):
        calls.append("mark_enqueued")
        return job

    async def commit():
        calls.append("commit")

    async def enqueue(**kwargs):
        calls.append("enqueue")
        return arq_job

    job_service = SimpleNamespace(
        create_job_from_request=AsyncMock(side_effect=create_job),
        mark_enqueued=AsyncMock(side_effect=mark_enqueued),
    )
    queue_service = SimpleNamespace(
        enqueue_command_job=AsyncMock(side_effect=enqueue)
    )
    monkeypatch.setattr(
        job_dispatch_service,
        "JobService",
        lambda session: job_service,
    )
    monkeypatch.setattr(
        job_dispatch_service,
        "QueueService",
        lambda redis: queue_service,
    )
    session = SimpleNamespace(commit=AsyncMock(side_effect=commit))

    dispatched = await JobDispatchService(
        session,
        SimpleNamespace(),
    ).create_and_enqueue(
        endpoint="/api/v1/events/search",
        method="POST",
        command="events.search",
        input_payload={"place_query": "Москва"},
    )

    assert calls == ["create", "commit", "enqueue", "mark_enqueued", "commit"]
    assert dispatched.job is job
    assert dispatched.arq_job is arq_job
    queue_service.enqueue_command_job.assert_awaited_once_with(
        job_id=job.id,
        command=job.command,
    )
    job_service.mark_enqueued.assert_awaited_once_with(
        job_id=job.id,
        queue_job_id=arq_job.job_id,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "enqueue_side_effect",
    [None, ConnectionError("redis unavailable")],
)
async def test_dispatch_marks_job_failed_when_enqueue_does_not_succeed(
    monkeypatch,
    enqueue_side_effect,
):
    job = SimpleNamespace(
        id=uuid4(),
        command="events.search",
        status="queued",
        error_type=None,
        error_message=None,
    )
    events: list[str] = []

    async def create_job(**kwargs):
        events.append("create")
        return job

    async def get_job(job_id):
        events.append("load")
        return job

    async def mark_failed(target, *, error_type, error_message):
        events.append("mark_failed")
        target.status = "failed"
        target.error_type = error_type
        target.error_message = error_message

    async def add_event(**kwargs):
        events.append(kwargs["event_type"])

    async def commit():
        events.append("commit")

    async def enqueue(**kwargs):
        events.append("enqueue")
        if isinstance(enqueue_side_effect, Exception):
            raise enqueue_side_effect
        return enqueue_side_effect

    job_service = SimpleNamespace(
        create_job_from_request=AsyncMock(side_effect=create_job),
        get_by_id=AsyncMock(side_effect=get_job),
        job_repo=SimpleNamespace(
            mark_failed=AsyncMock(side_effect=mark_failed),
            add_event=AsyncMock(side_effect=add_event),
        ),
        mark_enqueued=AsyncMock(),
    )
    queue_service = SimpleNamespace(
        enqueue_command_job=AsyncMock(side_effect=enqueue)
    )
    monkeypatch.setattr(
        job_dispatch_service,
        "JobService",
        lambda session: job_service,
    )
    monkeypatch.setattr(
        job_dispatch_service,
        "QueueService",
        lambda redis: queue_service,
    )
    session = SimpleNamespace(commit=AsyncMock(side_effect=commit))

    with pytest.raises(JobEnqueueError) as exc_info:
        await JobDispatchService(
            session,
            SimpleNamespace(),
        ).create_and_enqueue(
            endpoint="/api/v1/events/search",
            method="POST",
            command="events.search",
            input_payload={},
        )

    assert exc_info.value.job_id == job.id
    assert events == [
        "create",
        "commit",
        "enqueue",
        "load",
        "mark_failed",
        "enqueue_failed",
        "commit",
    ]
    assert job.status == "failed"
    assert job.error_type == "JobEnqueueError"
    assert job.error_message == "The job could not be enqueued for processing."
    job_service.mark_enqueued.assert_not_awaited()


@pytest.mark.asyncio
async def test_generic_worker_runs_existing_job_and_commits(monkeypatch):
    session = _SessionContext()
    output = CommandOutput(
        status="ok",
        result_type="events.search",
        items=[],
        meta={},
        result_payload={"status": "ok"},
    )
    command_executor = SimpleNamespace(
        run_existing_job=AsyncMock(return_value=output)
    )
    monkeypatch.setattr(tasks, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(tasks, "CommandExecutor", lambda _: command_executor)
    job_id = uuid4()

    result = await tasks.process_command_job({}, str(job_id))

    assert result == {
        "status": "ok",
        "job_id": str(job_id),
        "result_status": "ok",
    }
    command_executor.run_existing_job.assert_awaited_once_with(
        job_id,
        source="worker",
    )
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_generic_worker_commits_failure_diagnostics_and_reraises(monkeypatch):
    session = _SessionContext()
    command_executor = SimpleNamespace(
        run_existing_job=AsyncMock(side_effect=RuntimeError("failed"))
    )
    monkeypatch.setattr(tasks, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(tasks, "CommandExecutor", lambda _: command_executor)

    with pytest.raises(RuntimeError, match="failed"):
        await tasks.process_command_job({}, str(uuid4()))

    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_succeeded_job_reuses_persisted_command_result_without_execution():
    job_id = uuid4()
    job = SimpleNamespace(
        id=job_id,
        status="succeeded",
        command="events.search",
        input_payload={},
        result_payload={"status": "ok", "items": [{"id": 1}]},
    )
    stored_result = SimpleNamespace(
        result_type="events",
        items=[{"id": 1}],
        meta={"source": "worker", "returned": 1},
    )
    command_executor = CommandExecutor(SimpleNamespace())
    command_executor.job_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=job)
    )
    command_executor.result_repo = SimpleNamespace(
        get_latest_by_job_id=AsyncMock(return_value=stored_result),
        create=AsyncMock(),
    )
    command_executor.run_payload = AsyncMock()

    output = await command_executor.run_existing_job(job_id)

    assert output.result_type == "events"
    assert output.items == stored_result.items
    assert output.meta == stored_result.meta
    command_executor.run_payload.assert_not_awaited()
    command_executor.result_repo.create.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("router_module", "endpoint", "payload", "command", "request_text"),
    [
        (
            geo,
            geo.resolve_geo,
            _Payload(dumped={"query": "Москва"}, query="Москва"),
            "geo.resolve",
            "Москва",
        ),
        (
            events,
            events.search_events,
            _Payload(dumped={"place_query": "Москва"}, place_query="Москва"),
            "events.search",
            "Москва",
        ),
        (
            places,
            places.search_places,
            _Payload(dumped={"place_query": "Москва"}, place_query="Москва"),
            "places.search",
            "Москва",
        ),
        (
            movies,
            movies.search_movies,
            _Payload(dumped={"place_query": "Москва"}, place_query="Москва"),
            "movies.search",
            "Москва",
        ),
        (
            movie_showings,
            movie_showings.search_movie_showings,
            _Payload(dumped={"place_query": "Москва"}, place_query="Москва"),
            "movie_showings.search",
            "Москва",
        ),
        (
            news,
            news.search_news,
            _Payload(dumped={"place_query": "Москва"}, place_query="Москва"),
            "news.search",
            "Москва",
        ),
        (
            lists,
            lists.search_lists,
            _Payload(dumped={"place_query": "Москва"}, place_query="Москва"),
            "lists.search",
            "Москва",
        ),
        (
            routing,
            routing.plan_transit_route,
            _Payload(
                dumped={"origin_lat": 55.842},
                origin_lat=55.842,
                origin_lon=37.18,
                destination_lat=55.751,
                destination_lon=37.617,
            ),
            "routing.transit.plan",
            "55.842,37.18 -> 55.751,37.617",
        ),
        (
            routing,
            routing.plan_street_route,
            _Payload(
                dumped={"origin_lat": 55.842},
                origin_lat=55.842,
                origin_lon=37.18,
                destination_lat=55.751,
                destination_lon=37.617,
            ),
            "routing.street.plan",
            "55.842,37.18 -> 55.751,37.617",
        ),
    ],
)
async def test_all_queued_rest_endpoints_use_generic_dispatcher(
    monkeypatch,
    router_module,
    endpoint,
    payload,
    command,
    request_text,
):
    job_id = uuid4()
    dispatch_service = SimpleNamespace(
        create_and_enqueue=AsyncMock(
            return_value=SimpleNamespace(
                job=SimpleNamespace(id=job_id),
                arq_job=SimpleNamespace(job_id=f"{command}:{job_id}"),
            )
        )
    )
    session = SimpleNamespace()
    redis = SimpleNamespace()
    monkeypatch.setattr(
        router_module,
        "JobDispatchService",
        lambda actual_session, actual_redis: dispatch_service,
    )

    response = await endpoint(payload, session, redis)

    assert response.job_id == job_id
    assert response.queue_job_id == f"{command}:{job_id}"
    assert response.enqueued is True
    kwargs = dispatch_service.create_and_enqueue.await_args.kwargs
    assert kwargs["command"] == command
    assert kwargs["request_text"] == request_text
    assert kwargs["input_payload"] == payload.dumped


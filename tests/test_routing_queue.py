from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.routers import routing
from app.api.routers.jobs import compact_result_payload
from app.schemas.routing import StreetRouteRequest, TransitRouteRequest
from app.services.queue_service import QueueService
from app.workers.tasks import (
    process_street_routing_job,
    process_transit_routing_job,
)
from app.workers.worker_settings import WorkerSettings


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "function_name", "job_id_prefix"),
    [
        (
            "enqueue_transit_routing_job",
            "process_transit_routing_job",
            "routing.transit.plan",
        ),
        (
            "enqueue_street_routing_job",
            "process_street_routing_job",
            "routing.street.plan",
        ),
    ],
)
async def test_routing_queue_uses_stable_job_ids(
    method_name,
    function_name,
    job_id_prefix,
):
    job_id = uuid4()
    redis = SimpleNamespace(
        enqueue_job=AsyncMock(return_value=SimpleNamespace(job_id="arq-id"))
    )

    result = await getattr(QueueService(redis), method_name)(job_id)

    assert result == "arq-id"
    redis.enqueue_job.assert_awaited_once_with(
        function_name,
        str(job_id),
        _job_id=f"{job_id_prefix}:{job_id}",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("endpoint", "command", "queue_method", "request_factory"),
    [
        (
            routing.plan_transit_route,
            "routing.transit.plan",
            "enqueue_transit_routing_job",
            TransitRouteRequest,
        ),
        (
            routing.plan_street_route,
            "routing.street.plan",
            "enqueue_street_routing_job",
            StreetRouteRequest,
        ),
    ],
)
async def test_routing_rest_endpoints_create_and_enqueue_jobs(
    monkeypatch,
    endpoint,
    command,
    queue_method,
    request_factory,
):
    job_id = uuid4()
    job_service = SimpleNamespace(
        create_job_from_api_request=AsyncMock(
            return_value=SimpleNamespace(id=job_id)
        ),
        mark_enqueued=AsyncMock(),
    )
    queue_service = SimpleNamespace()
    setattr(queue_service, queue_method, AsyncMock(return_value="queue-id"))
    monkeypatch.setattr(routing, "JobService", lambda session: job_service)
    monkeypatch.setattr(routing, "QueueService", lambda redis: queue_service)
    session = SimpleNamespace(commit=AsyncMock())
    request = request_factory(
        origin_lat=55.842,
        origin_lon=37.180,
        destination_lat=55.751,
        destination_lon=37.617,
    )

    response = await endpoint(request, session, SimpleNamespace())

    assert response.job_id == job_id
    assert response.queue_job_id == "queue-id"
    assert response.enqueued is True
    create_kwargs = job_service.create_job_from_api_request.await_args.kwargs
    assert create_kwargs["command"] == command
    assert create_kwargs["request_text"] == "55.842,37.18 -> 55.751,37.617"
    assert create_kwargs["input_payload"]["origin_lat"] == 55.842
    job_service.mark_enqueued.assert_awaited_once_with(
        job_id=job_id,
        queue_job_id="queue-id",
    )
    session.commit.assert_awaited_once()


def test_routing_worker_functions_are_registered_without_timeout_changes():
    assert process_transit_routing_job in WorkerSettings.functions
    assert process_street_routing_job in WorkerSettings.functions
    assert process_transit_routing_job.__name__ == "process_transit_routing_job"
    assert process_street_routing_job.__name__ == "process_street_routing_job"
    assert WorkerSettings.max_jobs == 10
    assert WorkerSettings.job_timeout == 120
    assert WorkerSettings.keep_result == 3600


def test_default_job_response_hides_full_routes():
    compact = compact_result_payload(
        {
            "status": "ok",
            "routes": [{"geometry": "encoded-polyline"}],
            "warnings": [],
        }
    )

    assert compact is not None
    assert "routes" not in compact
    assert compact["routes_hidden"] is True
    assert compact["routes_count"] == 1
    assert compact["warnings"] == []

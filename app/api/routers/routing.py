from fastapi import APIRouter

from app.api.deps import ArqPool, DbSession
from app.schemas.routing import (
    RoutingQueuedResponse,
    StreetRouteRequest,
    TransitRouteRequest,
)
from app.services.job_service import JobService
from app.services.queue_service import QueueService


router = APIRouter(prefix="/routing", tags=["routing"])


@router.post("/transit", response_model=RoutingQueuedResponse)
async def plan_transit_route(
    payload: TransitRouteRequest,
    session: DbSession,
    redis: ArqPool,
):
    job_service = JobService(session)
    job = await job_service.create_job_from_api_request(
        endpoint="/api/v1/routing/transit",
        method="POST",
        command="routing.transit.plan",
        input_payload=payload.model_dump(mode="json"),
        request_text=_request_text(payload),
    )

    queue_job_id = await QueueService(redis).enqueue_transit_routing_job(job.id)
    await job_service.mark_enqueued(
        job_id=job.id,
        queue_job_id=queue_job_id,
    )
    await session.commit()
    return RoutingQueuedResponse(
        status="ok",
        job_id=job.id,
        queue_job_id=queue_job_id,
        enqueued=queue_job_id is not None,
    )


@router.post("/street", response_model=RoutingQueuedResponse)
async def plan_street_route(
    payload: StreetRouteRequest,
    session: DbSession,
    redis: ArqPool,
):
    job_service = JobService(session)
    job = await job_service.create_job_from_api_request(
        endpoint="/api/v1/routing/street",
        method="POST",
        command="routing.street.plan",
        input_payload=payload.model_dump(mode="json"),
        request_text=_request_text(payload),
    )

    queue_job_id = await QueueService(redis).enqueue_street_routing_job(job.id)
    await job_service.mark_enqueued(
        job_id=job.id,
        queue_job_id=queue_job_id,
    )
    await session.commit()
    return RoutingQueuedResponse(
        status="ok",
        job_id=job.id,
        queue_job_id=queue_job_id,
        enqueued=queue_job_id is not None,
    )


def _request_text(payload: TransitRouteRequest | StreetRouteRequest) -> str:
    return (
        f"{payload.origin_lat},{payload.origin_lon} -> "
        f"{payload.destination_lat},{payload.destination_lon}"
    )

from fastapi import APIRouter

from app.api.deps import ArqPool, DbSession
from app.schemas.routing import (
    RoutingQueuedResponse,
    StreetRouteRequest,
    TransitRouteRequest,
)
from app.services.job_dispatch_service import JobDispatchService


router = APIRouter(prefix="/routing", tags=["routing"])


@router.post("/transit", response_model=RoutingQueuedResponse)
async def plan_transit_route(
    payload: TransitRouteRequest,
    session: DbSession,
    redis: ArqPool,
):
    dispatch = await JobDispatchService(session, redis).create_and_enqueue(
        endpoint="/api/v1/routing/transit",
        method="POST",
        command="routing.transit.plan",
        input_payload=payload.model_dump(mode="json"),
        request_text=_request_text(payload),
    )

    return RoutingQueuedResponse(
        status="ok",
        job_id=dispatch.job.id,
        queue_job_id=dispatch.arq_job.job_id,
        enqueued=True,
    )


@router.post("/street", response_model=RoutingQueuedResponse)
async def plan_street_route(
    payload: StreetRouteRequest,
    session: DbSession,
    redis: ArqPool,
):
    dispatch = await JobDispatchService(session, redis).create_and_enqueue(
        endpoint="/api/v1/routing/street",
        method="POST",
        command="routing.street.plan",
        input_payload=payload.model_dump(mode="json"),
        request_text=_request_text(payload),
    )

    return RoutingQueuedResponse(
        status="ok",
        job_id=dispatch.job.id,
        queue_job_id=dispatch.arq_job.job_id,
        enqueued=True,
    )


def _request_text(payload: TransitRouteRequest | StreetRouteRequest) -> str:
    return (
        f"{payload.origin_lat},{payload.origin_lon} -> "
        f"{payload.destination_lat},{payload.destination_lon}"
    )

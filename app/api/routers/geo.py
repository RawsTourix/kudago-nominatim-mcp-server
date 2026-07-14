from fastapi import APIRouter

from app.api.deps import ArqPool, DbSession
from app.schemas.geo import GeoResolveQueuedResponse, GeoResolveRequest
from app.services.job_dispatch_service import JobDispatchService


router = APIRouter(prefix="/geo", tags=["geo"])


@router.post("/resolve", response_model=GeoResolveQueuedResponse)
async def resolve_geo(
    payload: GeoResolveRequest,
    session: DbSession,
    redis: ArqPool,
):
    dispatch = await JobDispatchService(session, redis).create_and_enqueue(
        endpoint="/api/v1/geo/resolve",
        method="POST",
        command="geo.resolve",
        input_payload=payload.model_dump(),
        request_text=payload.query,
    )

    return GeoResolveQueuedResponse(
        status="ok",
        job_id=dispatch.job.id,
        queue_job_id=dispatch.arq_job.job_id,
        enqueued=True,
    )

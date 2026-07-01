from fastapi import APIRouter

from app.api.deps import ArqPool, DbSession
from app.schemas.geo import GeoResolveQueuedResponse, GeoResolveRequest
from app.services.job_service import JobService
from app.services.queue_service import QueueService


router = APIRouter(prefix="/geo", tags=["geo"])


@router.post("/resolve", response_model=GeoResolveQueuedResponse)
async def resolve_geo(
    payload: GeoResolveRequest,
    session: DbSession,
    redis: ArqPool,
):
    job_service = JobService(session)
    job = await job_service.create_job_from_api_request(
        endpoint="/api/v1/geo/resolve",
        method="POST",
        command="geo.resolve",
        input_payload=payload.model_dump(),
        request_text=payload.query,
    )

    queue_service = QueueService(redis)
    queue_job_id = await queue_service.enqueue_geo_resolve_job(job.id)
    await job_service.mark_enqueued(
        job_id=job.id,
        queue_job_id=queue_job_id,
    )
    await session.commit()

    return GeoResolveQueuedResponse(
        status="ok",
        job_id=job.id,
        queue_job_id=queue_job_id,
        enqueued=queue_job_id is not None,
    )

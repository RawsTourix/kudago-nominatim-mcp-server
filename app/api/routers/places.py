from fastapi import APIRouter

from app.api.deps import ArqPool, DbSession
from app.schemas.places import PlacesSearchQueuedResponse, PlacesSearchRequest
from app.services.job_dispatch_service import JobDispatchService


router = APIRouter(prefix="/places", tags=["places"])


@router.post("/search", response_model=PlacesSearchQueuedResponse)
async def search_places(
    payload: PlacesSearchRequest,
    session: DbSession,
    redis: ArqPool,
):
    dispatch = await JobDispatchService(session, redis).create_and_enqueue(
        endpoint="/api/v1/places/search",
        method="POST",
        command="places.search",
        input_payload=payload.model_dump(),
        request_text=payload.place_query,
    )

    return PlacesSearchQueuedResponse(
        status="ok",
        job_id=dispatch.job.id,
        queue_job_id=dispatch.arq_job.job_id,
        enqueued=True,
    )

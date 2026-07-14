from fastapi import APIRouter

from app.api.deps import ArqPool, DbSession
from app.schemas.events import EventsSearchQueuedResponse, EventsSearchRequest
from app.services.job_dispatch_service import JobDispatchService


router = APIRouter(prefix="/events", tags=["events"])


@router.post("/search", response_model=EventsSearchQueuedResponse)
async def search_events(
    payload: EventsSearchRequest,
    session: DbSession,
    redis: ArqPool,
):
    dispatch = await JobDispatchService(session, redis).create_and_enqueue(
        endpoint="/api/v1/events/search",
        method="POST",
        command="events.search",
        input_payload=payload.model_dump(),
        request_text=payload.place_query,
    )

    return EventsSearchQueuedResponse(
        status="ok",
        job_id=dispatch.job.id,
        queue_job_id=dispatch.arq_job.job_id,
        enqueued=True,
    )

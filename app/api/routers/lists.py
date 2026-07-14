from fastapi import APIRouter

from app.api.deps import ArqPool, DbSession
from app.schemas.lists import ListsSearchQueuedResponse, ListsSearchRequest
from app.services.job_dispatch_service import JobDispatchService


router = APIRouter(prefix="/lists", tags=["lists"])


@router.post("/search", response_model=ListsSearchQueuedResponse)
async def search_lists(
    payload: ListsSearchRequest,
    session: DbSession,
    redis: ArqPool,
):
    dispatch = await JobDispatchService(session, redis).create_and_enqueue(
        endpoint="/api/v1/lists/search",
        method="POST",
        command="lists.search",
        input_payload=payload.model_dump(),
        request_text=payload.place_query,
    )

    return ListsSearchQueuedResponse(
        status="ok",
        job_id=dispatch.job.id,
        queue_job_id=dispatch.arq_job.job_id,
        enqueued=True,
    )

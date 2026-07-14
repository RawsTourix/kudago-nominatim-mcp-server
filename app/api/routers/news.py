from fastapi import APIRouter

from app.api.deps import ArqPool, DbSession
from app.schemas.news import NewsSearchQueuedResponse, NewsSearchRequest
from app.services.job_dispatch_service import JobDispatchService


router = APIRouter(prefix="/news", tags=["news"])


@router.post("/search", response_model=NewsSearchQueuedResponse)
async def search_news(
    payload: NewsSearchRequest,
    session: DbSession,
    redis: ArqPool,
):
    dispatch = await JobDispatchService(session, redis).create_and_enqueue(
        endpoint="/api/v1/news/search",
        method="POST",
        command="news.search",
        input_payload=payload.model_dump(),
        request_text=payload.place_query,
    )

    return NewsSearchQueuedResponse(
        status="ok",
        job_id=dispatch.job.id,
        queue_job_id=dispatch.arq_job.job_id,
        enqueued=True,
    )

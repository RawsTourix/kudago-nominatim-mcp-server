from fastapi import APIRouter

from app.api.deps import ArqPool, DbSession
from app.schemas.news import NewsSearchQueuedResponse, NewsSearchRequest
from app.services.job_service import JobService
from app.services.queue_service import QueueService


router = APIRouter(prefix="/news", tags=["news"])


@router.post("/search", response_model=NewsSearchQueuedResponse)
async def search_news(
    payload: NewsSearchRequest,
    session: DbSession,
    redis: ArqPool,
):
    job_service = JobService(session)
    job = await job_service.create_job_from_api_request(
        endpoint="/api/v1/news/search",
        method="POST",
        command="news.search",
        input_payload=payload.model_dump(),
        request_text=payload.place_query,
    )

    queue_service = QueueService(redis)
    queue_job_id = await queue_service.enqueue_news_search_job(job.id)
    await job_service.mark_enqueued(
        job_id=job.id,
        queue_job_id=queue_job_id,
    )
    await session.commit()

    return NewsSearchQueuedResponse(
        status="ok",
        job_id=job.id,
        queue_job_id=queue_job_id,
        enqueued=queue_job_id is not None,
    )

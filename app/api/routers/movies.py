from fastapi import APIRouter

from app.api.deps import ArqPool, DbSession
from app.schemas.movies import MoviesSearchQueuedResponse, MoviesSearchRequest
from app.services.job_service import JobService
from app.services.queue_service import QueueService


router = APIRouter(prefix="/movies", tags=["movies"])


@router.post("/search", response_model=MoviesSearchQueuedResponse)
async def search_movies(
    payload: MoviesSearchRequest,
    session: DbSession,
    redis: ArqPool,
):
    job_service = JobService(session)
    job = await job_service.create_job_from_api_request(
        endpoint="/api/v1/movies/search",
        method="POST",
        command="movies.search",
        input_payload=payload.model_dump(),
        request_text=payload.place_query,
    )

    queue_service = QueueService(redis)
    queue_job_id = await queue_service.enqueue_movies_search_job(job.id)
    await job_service.mark_enqueued(
        job_id=job.id,
        queue_job_id=queue_job_id,
    )
    await session.commit()

    return MoviesSearchQueuedResponse(
        status="ok",
        job_id=job.id,
        queue_job_id=queue_job_id,
        enqueued=queue_job_id is not None,
    )

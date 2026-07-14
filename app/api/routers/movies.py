from fastapi import APIRouter

from app.api.deps import ArqPool, DbSession
from app.schemas.movies import MoviesSearchQueuedResponse, MoviesSearchRequest
from app.services.job_dispatch_service import JobDispatchService


router = APIRouter(prefix="/movies", tags=["movies"])


@router.post("/search", response_model=MoviesSearchQueuedResponse)
async def search_movies(
    payload: MoviesSearchRequest,
    session: DbSession,
    redis: ArqPool,
):
    dispatch = await JobDispatchService(session, redis).create_and_enqueue(
        endpoint="/api/v1/movies/search",
        method="POST",
        command="movies.search",
        input_payload=payload.model_dump(),
        request_text=payload.place_query,
    )

    return MoviesSearchQueuedResponse(
        status="ok",
        job_id=dispatch.job.id,
        queue_job_id=dispatch.arq_job.job_id,
        enqueued=True,
    )

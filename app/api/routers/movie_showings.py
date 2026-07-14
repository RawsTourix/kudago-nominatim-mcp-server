from fastapi import APIRouter

from app.api.deps import ArqPool, DbSession
from app.schemas.movie_showings import (
    MovieShowingsSearchQueuedResponse,
    MovieShowingsSearchRequest,
)
from app.services.job_dispatch_service import JobDispatchService


router = APIRouter(prefix="/movie-showings", tags=["movie-showings"])


@router.post("/search", response_model=MovieShowingsSearchQueuedResponse)
async def search_movie_showings(
    payload: MovieShowingsSearchRequest,
    session: DbSession,
    redis: ArqPool,
):
    dispatch = await JobDispatchService(session, redis).create_and_enqueue(
        endpoint="/api/v1/movie-showings/search",
        method="POST",
        command="movie_showings.search",
        input_payload=payload.model_dump(),
        request_text=payload.place_query,
    )

    return MovieShowingsSearchQueuedResponse(
        status="ok",
        job_id=dispatch.job.id,
        queue_job_id=dispatch.arq_job.job_id,
        enqueued=True,
    )

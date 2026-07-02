from uuid import UUID

from arq.connections import ArqRedis


class QueueService:
    def __init__(self, redis: ArqRedis):
        self.redis = redis

    async def enqueue_test_job(self, job_id: UUID) -> str | None:
        queue_job_id = f"test:{job_id}"

        job = await self.redis.enqueue_job(
            "process_test_job",
            str(job_id),
            _job_id=queue_job_id,
        )

        return job.job_id if job is not None else None

    async def enqueue_geo_resolve_job(self, job_id: UUID) -> str | None:
        queue_job_id = f"geo.resolve:{job_id}"
        job = await self.redis.enqueue_job(
            "process_geo_resolve_job",
            str(job_id),
            _job_id=queue_job_id,
        )
        return job.job_id if job is not None else None

    async def enqueue_events_search_job(self, job_id: UUID) -> str | None:
        queue_job_id = f"events.search:{job_id}"
        job = await self.redis.enqueue_job(
            "process_events_search_job",
            str(job_id),
            _job_id=queue_job_id,
        )
        return job.job_id if job is not None else None

    async def enqueue_places_search_job(self, job_id: UUID) -> str | None:
        queue_job_id = f"places.search:{job_id}"
        job = await self.redis.enqueue_job(
            "process_places_search_job",
            str(job_id),
            _job_id=queue_job_id,
        )
        return job.job_id if job is not None else None

    async def enqueue_movie_showings_search_job(self, job_id: UUID) -> str | None:
        queue_job_id = f"movie_showings.search:{job_id}"
        job = await self.redis.enqueue_job(
            "process_movie_showings_search_job",
            str(job_id),
            _job_id=queue_job_id,
        )
        return job.job_id if job is not None else None

    async def enqueue_movies_search_job(self, job_id: UUID) -> str | None:
        queue_job_id = f"movies.search:{job_id}"
        job = await self.redis.enqueue_job(
            "process_movies_search_job",
            str(job_id),
            _job_id=queue_job_id,
        )
        return job.job_id if job is not None else None

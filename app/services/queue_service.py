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

        if job is None:
            return None

        return job.job_id
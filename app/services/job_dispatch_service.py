from dataclasses import dataclass
from typing import Any
from uuid import UUID

from arq.connections import ArqRedis
from arq.jobs import Job as ArqJob
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.services.job_service import JobService
from app.services.queue_service import QueueService


class JobEnqueueError(RuntimeError):
    def __init__(self, message: str, *, job_id: UUID | None = None):
        super().__init__(message)
        self.job_id = job_id


@dataclass(slots=True)
class DispatchedJob:
    job: Job
    arq_job: ArqJob


class JobDispatchService:
    def __init__(
        self,
        session: AsyncSession,
        redis: ArqRedis,
    ):
        self.session = session
        self.redis = redis
        self.job_service = JobService(session)
        self.queue_service = QueueService(redis)

    async def create_and_enqueue(
        self,
        *,
        endpoint: str,
        method: str,
        command: str,
        input_payload: dict[str, Any],
        request_text: str | None = None,
        client_request_id: str | None = None,
    ) -> DispatchedJob:
        job = await self.job_service.create_job_from_request(
            endpoint=endpoint,
            method=method,
            command=command,
            input_payload=input_payload,
            request_text=request_text,
            client_request_id=client_request_id,
        )
        await self.session.commit()

        try:
            arq_job = await self.queue_service.enqueue_command_job(
                job_id=job.id,
                command=job.command,
            )
            if arq_job is None:
                raise JobEnqueueError(
                    "A job with the same queue identifier already exists.",
                    job_id=job.id,
                )
        except Exception as exc:
            await self._mark_enqueue_failed(job.id)
            if isinstance(exc, JobEnqueueError):
                raise
            raise JobEnqueueError(
                "The job could not be enqueued for processing.",
                job_id=job.id,
            ) from exc

        await self.job_service.mark_enqueued(
            job_id=job.id,
            queue_job_id=arq_job.job_id,
        )
        await self.session.commit()
        return DispatchedJob(job=job, arq_job=arq_job)

    async def _mark_enqueue_failed(self, job_id: UUID) -> None:
        job = await self.job_service.get_by_id(job_id)
        if job is not None:
            message = "The job could not be enqueued for processing."
            await self.job_service.job_repo.mark_failed(
                job,
                error_type="JobEnqueueError",
                error_message=message,
            )
            await self.job_service.job_repo.add_event(
                job_id=job.id,
                event_type="enqueue_failed",
                message=message,
                data={"error_type": "JobEnqueueError"},
            )
        await self.session.commit()

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JobRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        command: str,
        input_payload: dict[str, Any],
    ) -> Job:
        job = Job(
            command=command,
            status="queued",
            input_payload=input_payload,
        )
        self.session.add(job)
        await self.session.flush()
        return job

    async def get_by_id(self, job_id: uuid.UUID) -> Job | None:
        result = await self.session.execute(
            select(Job).where(Job.id == job_id)
        )
        return result.scalar_one_or_none()

    async def mark_running(self, job: Job) -> Job:
        job.status = "running"
        job.started_at = utc_now()
        job.attempts += 1
        await self.session.flush()
        return job

    async def mark_succeeded(self, job: Job, result_payload: dict[str, Any]) -> Job:
        job.status = "succeeded"
        job.result_payload = result_payload
        job.finished_at = utc_now()
        await self.session.flush()
        return job

    async def mark_failed(self, job: Job, error_type: str, error_message: str) -> Job:
        job.status = "failed"
        job.error_type = error_type
        job.error_message = error_message
        job.finished_at = utc_now()
        await self.session.flush()
        return job
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.repositories.job_repository import JobRepository
from app.repositories.request_repository import RequestRepository
from app.repositories.result_repository import ResultRepository


class JobService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.request_repo = RequestRepository(session)
        self.job_repo = JobRepository(session)
        self.result_repo = ResultRepository(session)

    async def create_job_from_api_request(
        self,
        *,
        endpoint: str,
        method: str,
        command: str,
        input_payload: dict[str, Any],
        request_text: str | None = None,
        client_request_id: str | None = None,
    ) -> Job:
        api_request = await self.request_repo.create(
            endpoint=endpoint,
            method=method,
            request_params=input_payload,
            request_text=request_text,
            client_request_id=client_request_id,
        )

        job = await self.job_repo.create(
            api_request_id=api_request.id,
            command=command,
            input_payload=input_payload,
        )

        await self.job_repo.add_event(
            job_id=job.id,
            event_type="queued",
            message="Job created from API request",
            data={
                "endpoint": endpoint,
                "method": method,
                "command": command,
            },
        )

        return job

    async def get_by_id(self, job_id: uuid.UUID) -> Job | None:
        return await self.job_repo.get_by_id(job_id)

    async def run_test_job(self, job_id: uuid.UUID) -> Job | None:
        job = await self.job_repo.get_by_id(job_id)

        if job is None:
            return None

        if job.status == "succeeded":
            return job

        await self.job_repo.mark_running(job)

        await self.job_repo.add_event(
            job_id=job.id,
            event_type="started",
            message="Test job execution started",
            data={
                "command": job.command,
                "attempts": job.attempts,
            },
        )

        result_payload: dict[str, Any] = {
            "status": "ok",
            "command": job.command,
            "echo": job.input_payload,
            "message": "Test job executed successfully",
        }

        await self.result_repo.create(
            job_id=job.id,
            result_type="test",
            items=[
                {
                    "command": job.command,
                    "input": job.input_payload,
                    "output": result_payload,
                }
            ],
            meta={
                "source": "run_test_job",
                "items_count": 1,
            },
        )

        await self.job_repo.mark_succeeded(
            job,
            result_payload=result_payload,
        )

        await self.job_repo.add_event(
            job_id=job.id,
            event_type="completed",
            message="Test job execution completed",
            data={"status": job.status},
        )

        return job

    async def get_job_from_api_request(
        self,
        *,
        api_request_id: uuid.UUID,
    ) -> Job | None:
        return await self.job_repo.get_by_api_request_id(api_request_id)

    async def get_job_by_client_request_id(
        self,
        *,
        client_request_id: str,
    ) -> Job | None:
        api_request = await self.request_repo.get_by_client_request_id(
            client_request_id
        )

        if api_request is None:
            return None

        return await self.job_repo.get_by_api_request_id(api_request.id)

    async def mark_enqueued(
        self,
        *,
        job_id,
        queue_job_id: str | None,
    ) -> Job | None:
        job = await self.job_repo.get_by_id(job_id)

        if job is None:
            return None

        await self.job_repo.set_queue_job_id(job, queue_job_id)

        await self.job_repo.add_event(
            job_id=job.id,
            event_type="enqueued",
            message="Job enqueued to Redis",
            data={
                "queue_job_id": queue_job_id,
            },
        )

        return job
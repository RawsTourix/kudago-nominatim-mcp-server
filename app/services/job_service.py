import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.repositories.job_repository import JobRepository
from app.repositories.request_repository import RequestRepository


class JobService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.request_repo = RequestRepository(session)
        self.job_repo = JobRepository(session)

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
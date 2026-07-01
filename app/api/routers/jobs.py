from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.api.deps import DbSession
from app.repositories.job_repository import JobRepository
from app.schemas.jobs import JobCreateRequest, JobCreateResponse, JobGetResponse, JobResponse


router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobCreateResponse)
async def create_job(payload: JobCreateRequest, session: DbSession):
    repo = JobRepository(session)

    job = await repo.create(
        command=payload.command,
        input_payload=payload.input_payload,
    )

    await session.commit()

    return JobCreateResponse(
        status="ok",
        job_id=job.id,
    )


@router.get("/{job_id}", response_model=JobGetResponse)
async def get_job(job_id: UUID, session: DbSession):
    repo = JobRepository(session)
    job = await repo.get_by_id(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobGetResponse(
        status="ok",
        job=JobResponse(
            id=job.id,
            command=job.command,
            status=job.status,
            attempts=job.attempts,
            max_attempts=job.max_attempts,
            input_payload=job.input_payload,
            result_payload=job.result_payload,
            error_type=job.error_type,
            error_message=job.error_message,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        ),
    )
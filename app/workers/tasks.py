from uuid import UUID

from app.core.db import AsyncSessionLocal
from app.repositories.job_repository import JobRepository
from app.services.job_service import JobService


async def process_test_job(ctx, job_id: str) -> dict:
    parsed_job_id = UUID(job_id)

    async with AsyncSessionLocal() as session:
        service = JobService(session)
        job_repo = JobRepository(session)

        job = await job_repo.get_by_id(parsed_job_id)

        if job is None:
            return {
                "status": "error",
                "message": "Job not found",
                "job_id": job_id,
            }

        if job.status == "succeeded":
            return {
                "status": "ok",
                "message": "Job already succeeded",
                "job_id": job_id,
            }

        try:
            job = await service.run_test_job(parsed_job_id)
            await session.commit()

            return {
                "status": "ok",
                "job_id": job_id,
                "job_status": job.status if job else None,
            }

        except Exception as exc:
            if job is not None:
                await job_repo.mark_failed(
                    job,
                    error_type=exc.__class__.__name__,
                    error_message=str(exc),
                )

                await job_repo.add_event(
                    job_id=job.id,
                    event_type="failed",
                    message="Worker task failed",
                    data={
                        "error_type": exc.__class__.__name__,
                        "error_message": str(exc),
                    },
                )

            await session.commit()
            raise
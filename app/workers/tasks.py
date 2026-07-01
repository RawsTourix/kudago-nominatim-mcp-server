from uuid import UUID

from app.core.db import AsyncSessionLocal
from app.repositories.job_repository import JobRepository
from app.repositories.result_repository import ResultRepository
from app.services.geo_service import GeoService
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


async def process_geo_resolve_job(ctx, job_id: str) -> dict:
    parsed_job_id = UUID(job_id)

    async with AsyncSessionLocal() as session:
        job_repo = JobRepository(session)
        result_repo = ResultRepository(session)
        geo_service = GeoService(session)
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
            await job_repo.mark_running(job)
            await job_repo.add_event(
                job_id=job.id,
                event_type="started",
                message="Geo resolve job started",
                data={"command": job.command},
            )

            payload = job.input_payload
            result_payload = await geo_service.resolve_place(
                job_id=job.id,
                query=payload["query"],
                countrycodes=payload.get("countrycodes", "ru"),
                limit=payload.get("limit", 5),
                accept_language=payload.get("accept_language", "ru"),
            )

            await result_repo.create(
                job_id=job.id,
                result_type="geo.resolve",
                items=result_payload.get("candidates", []),
                meta={
                    "status": result_payload["status"],
                    "source": result_payload["source"],
                    "query": result_payload["query"],
                    "selected_lat": result_payload.get("selected_lat"),
                    "selected_lon": result_payload.get("selected_lon"),
                    "radius": result_payload.get("radius"),
                },
            )
            await job_repo.mark_succeeded(job, result_payload=result_payload)
            await job_repo.add_event(
                job_id=job.id,
                event_type="completed",
                message="Geo resolve job completed",
                data={
                    "geo_status": result_payload["status"],
                    "source": result_payload["source"],
                },
            )
            await session.commit()

            return {
                "status": "ok",
                "job_id": job_id,
                "geo_status": result_payload["status"],
            }
        except Exception as exc:
            await job_repo.mark_failed(
                job,
                error_type=exc.__class__.__name__,
                error_message=str(exc),
            )
            await job_repo.add_event(
                job_id=job.id,
                event_type="failed",
                message="Geo resolve job failed",
                data={
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            await session.commit()
            raise

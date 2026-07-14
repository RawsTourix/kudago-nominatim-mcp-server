import asyncio
from typing import Any
from uuid import UUID

from app.application.contracts import CommandOutput
from app.application.executor import CommandExecutor
from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.repositories.job_repository import JobRepository
from app.services.job_service import JobService


DISPATCH_METADATA_WAIT_SECONDS = 3.0
DISPATCH_METADATA_POLL_SECONDS = 0.05


class CommandTimeoutError(TimeoutError):
    """The command exceeded the worker's internal execution budget."""


class DispatchMetadataMissingError(RuntimeError):
    """The dispatch transaction did not become visible to the worker in time."""


async def _mark_command_job_failed(
    job_id: UUID,
    *,
    error_type: str,
    error_message: str,
    event_message: str,
) -> None:
    async with AsyncSessionLocal() as session:
        job_repo = JobRepository(session)
        job = await job_repo.get_by_id(job_id)
        if job is None:
            return

        await job_repo.mark_failed(
            job,
            error_type=error_type,
            error_message=error_message,
        )
        await job_repo.add_event(
            job_id=job.id,
            event_type="failed",
            message=event_message,
            data={"error_type": error_type},
        )
        await session.commit()


async def _fail_if_dispatch_metadata_missing(job_id: UUID) -> bool:
    async with AsyncSessionLocal() as session:
        job_repo = JobRepository(session)
        job = await job_repo.get_by_id_for_update(job_id)
        if job is None:
            raise DispatchMetadataMissingError(f"Job not found: {job_id}")

        if job.queue_job_id is not None:
            return False

        error_message = (
            "Dispatch metadata was not persisted before worker execution."
        )
        await job_repo.mark_failed(
            job,
            error_type=DispatchMetadataMissingError.__name__,
            error_message=error_message,
        )
        await job_repo.add_event(
            job_id=job.id,
            event_type="failed",
            message="Dispatch metadata was not available",
            data={"error_type": DispatchMetadataMissingError.__name__},
        )
        await session.commit()
        return True


async def _wait_for_dispatch_metadata(
    job_id: UUID,
    *,
    timeout_seconds: float = DISPATCH_METADATA_WAIT_SECONDS,
    poll_interval_seconds: float = DISPATCH_METADATA_POLL_SECONDS,
) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds

    while True:
        async with AsyncSessionLocal() as session:
            job = await JobRepository(session).get_by_id(job_id)
            if job is not None and job.queue_job_id is not None:
                return

        remaining = deadline - loop.time()
        if remaining <= 0:
            break
        await asyncio.sleep(min(poll_interval_seconds, remaining))

    if await _fail_if_dispatch_metadata_missing(job_id):
        raise DispatchMetadataMissingError(
            "Dispatch metadata was not persisted before worker execution."
        )


async def _run_command_with_timeout(
    executor: CommandExecutor,
    job_id: UUID,
) -> CommandOutput:
    timeout_scope = asyncio.timeout(settings.command_job_timeout_seconds)
    try:
        async with timeout_scope:
            output = await executor.execute_started_job(
                job_id,
                source="worker",
            )
    except TimeoutError as exc:
        if timeout_scope.expired():
            raise CommandTimeoutError(
                "Command execution exceeded its timeout."
            ) from exc
        raise

    if timeout_scope.expired():
        raise CommandTimeoutError("Command execution exceeded its timeout.")
    return output


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


async def process_command_job(ctx, job_id: str) -> dict[str, Any]:
    parsed_job_id = UUID(job_id)
    await _wait_for_dispatch_metadata(parsed_job_id)

    async with AsyncSessionLocal() as session:
        executor = CommandExecutor(session)
        await executor.start_existing_job(parsed_job_id, source="worker")
        await session.commit()

    async with AsyncSessionLocal() as session:
        executor = CommandExecutor(session)

        try:
            output = await _run_command_with_timeout(executor, parsed_job_id)
            await session.commit()

            return {
                "status": "ok",
                "job_id": job_id,
                "result_status": output.status,
            }
        except CommandTimeoutError:
            await session.rollback()
            await _mark_command_job_failed(
                parsed_job_id,
                error_type=CommandTimeoutError.__name__,
                error_message="Command execution exceeded its timeout.",
                event_message="Command execution timed out",
            )
            raise
        except Exception:
            await session.commit()
            raise

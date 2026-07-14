from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.contracts import CommandOutput, ExecutionContext
from app.application.handlers import (
    EventsSearchHandler,
    GeoResolveHandler,
    ListsSearchHandler,
    MovieShowingsSearchHandler,
    MoviesSearchHandler,
    NewsSearchHandler,
    ObjectDetailHandler,
    PlacesSearchHandler,
    ReferenceHandler,
    StreetRoutingHandler,
    TransitRoutingHandler,
)
from app.models.job import Job
from app.repositories.job_repository import JobRepository
from app.repositories.result_repository import ResultRepository


HANDLERS = {
    GeoResolveHandler.command: GeoResolveHandler,
    EventsSearchHandler.command: EventsSearchHandler,
    PlacesSearchHandler.command: PlacesSearchHandler,
    NewsSearchHandler.command: NewsSearchHandler,
    ListsSearchHandler.command: ListsSearchHandler,
    MoviesSearchHandler.command: MoviesSearchHandler,
    MovieShowingsSearchHandler.command: MovieShowingsSearchHandler,
    ReferenceHandler.command: ReferenceHandler,
    ObjectDetailHandler.command: ObjectDetailHandler,
    TransitRoutingHandler.command: TransitRoutingHandler,
    StreetRoutingHandler.command: StreetRoutingHandler,
}


class CommandExecutor:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.job_repo = JobRepository(session)
        self.result_repo = ResultRepository(session)

    async def run_existing_job(
        self,
        job_id: UUID,
        *,
        source: str = "worker",
    ) -> CommandOutput:
        job = await self.job_repo.get_by_id(job_id)
        if job is None:
            raise ValueError(f"Job not found: {job_id}")

        if job.status == "succeeded" and job.result_payload is not None:
            return await self.load_completed_output(job_id)

        return await self.run_payload(
            job_id=job.id,
            command=job.command,
            payload=job.input_payload,
            source=source,
        )

    async def start_existing_job(
        self,
        job_id: UUID,
        *,
        source: str = "worker",
    ) -> bool:
        job = await self.job_repo.get_by_id(job_id)
        if job is None:
            raise ValueError(f"Job not found: {job_id}")

        if job.status == "succeeded" and job.result_payload is not None:
            return False

        await self.job_repo.mark_running(job)
        await self.job_repo.add_event(
            job_id=job.id,
            event_type="started",
            message=f"{job.command} execution started",
            data={"command": job.command, "source": source},
        )
        return True

    async def execute_started_job(
        self,
        job_id: UUID,
        *,
        source: str = "worker",
    ) -> CommandOutput:
        job = await self.job_repo.get_by_id(job_id)
        if job is None:
            raise ValueError(f"Job not found: {job_id}")

        if job.status == "succeeded" and job.result_payload is not None:
            return await self.load_completed_output(job_id)

        if job.status != "running":
            raise ValueError(
                f"Job execution has not been started: {job_id}; "
                f"status={job.status}"
            )

        context = ExecutionContext(
            job_id=job.id,
            command=job.command,
            source=source,
        )
        return await self._execute_payload(
            job=job,
            context=context,
            payload=job.input_payload,
        )

    async def load_completed_output(self, job_id: UUID) -> CommandOutput:
        job = await self.job_repo.get_by_id(job_id)

        if job is None:
            raise ValueError(f"Job not found: {job_id}")

        if job.status != "succeeded" or job.result_payload is None:
            raise ValueError(
                f"Job is not completed successfully: {job_id}; status={job.status}"
            )

        result = await self.result_repo.get_latest_by_job_id(job_id)
        if result is None:
            return self._completed_output(job.command, job.result_payload)

        return CommandOutput(
            status=str(job.result_payload.get("status", "ok")),
            result_type=result.result_type,
            items=result.items,
            meta=result.meta,
            result_payload=job.result_payload,
        )

    async def run_payload(
        self,
        *,
        job_id: UUID,
        command: str,
        payload: dict[str, Any],
        source: str,
        endpoint: str | None = None,
    ) -> CommandOutput:
        job = await self.job_repo.get_by_id(job_id)
        if job is None:
            raise ValueError(f"Job not found: {job_id}")

        context = ExecutionContext(
            job_id=job_id,
            command=command,
            source=source,
            endpoint=endpoint,
        )

        await self.job_repo.mark_running(job)
        await self.job_repo.add_event(
            job_id=job.id,
            event_type="started",
            message=f"{command} execution started",
            data={"command": command, "source": source},
        )
        return await self._execute_payload(
            job=job,
            context=context,
            payload=payload,
        )

    async def _execute_payload(
        self,
        *,
        job: Job,
        context: ExecutionContext,
        payload: dict[str, Any],
    ) -> CommandOutput:
        try:
            output = await self._dispatch(context, payload)
            for event in output.events:
                await self.job_repo.add_event(
                    job_id=job.id,
                    event_type=event.event_type,
                    message=event.message,
                    data=event.data,
                )

            await self.result_repo.create(
                job_id=job.id,
                result_type=output.result_type,
                items=output.items,
                meta=output.meta,
            )
            await self.job_repo.mark_succeeded(
                job,
                result_payload=output.result_payload,
            )
            await self.job_repo.add_event(
                job_id=job.id,
                event_type="completed",
                message=f"{context.command} execution completed",
                data={
                    "command": context.command,
                    "source": context.source,
                    "result_status": output.status,
                },
            )
            return output
        except Exception as exc:
            await self.job_repo.mark_failed(
                job,
                error_type=exc.__class__.__name__,
                error_message=str(exc),
            )
            await self.job_repo.add_event(
                job_id=job.id,
                event_type="failed",
                message=f"{context.command} execution failed",
                data={
                    "command": context.command,
                    "source": context.source,
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            raise

    async def _dispatch(
        self,
        context: ExecutionContext,
        payload: dict[str, Any],
    ) -> CommandOutput:
        handler_cls = HANDLERS.get(context.command)
        if handler_cls is None:
            raise ValueError(f"Unsupported command: {context.command}")
        return await handler_cls(self.session).run(context, payload)

    @staticmethod
    def _completed_output(
        command: str,
        result_payload: dict[str, Any],
    ) -> CommandOutput:
        items = result_payload.get("items")
        if not isinstance(items, list):
            items = result_payload.get("routes")
        if not isinstance(items, list):
            items = result_payload.get("candidates", [])

        return CommandOutput(
            status=str(result_payload.get("status", "ok")),
            result_type=command,
            items=items if isinstance(items, list) else [],
            meta={"reused_result": True},
            result_payload=result_payload,
        )

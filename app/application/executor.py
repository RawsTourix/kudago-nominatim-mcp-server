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
    PlacesSearchHandler,
)
from app.repositories.job_repository import JobRepository
from app.repositories.result_repository import ResultRepository


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
            return self._completed_output(job.command, job.result_payload)

        return await self.run_payload(
            job_id=job.id,
            command=job.command,
            payload=job.input_payload,
            source=source,
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

        try:
            await self.job_repo.mark_running(job)
            await self.job_repo.add_event(
                job_id=job.id,
                event_type="started",
                message=f"{command} execution started",
                data={"command": command, "source": source},
            )

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
                message=f"{command} execution completed",
                data={
                    "command": command,
                    "source": source,
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
                message=f"{command} execution failed",
                data={
                    "command": command,
                    "source": source,
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
        if context.command == GeoResolveHandler.command:
            return await GeoResolveHandler(self.session).run(context, payload)

        if context.command == EventsSearchHandler.command:
            return await EventsSearchHandler(self.session).run(context, payload)

        if context.command == PlacesSearchHandler.command:
            return await PlacesSearchHandler(self.session).run(context, payload)

        if context.command == NewsSearchHandler.command:
            return await NewsSearchHandler(self.session).run(context, payload)

        if context.command == ListsSearchHandler.command:
            return await ListsSearchHandler(self.session).run(context, payload)

        if context.command == MoviesSearchHandler.command:
            return await MoviesSearchHandler(self.session).run(context, payload)

        if context.command == MovieShowingsSearchHandler.command:
            return await MovieShowingsSearchHandler(self.session).run(
                context,
                payload,
            )

        raise ValueError(f"Unsupported command: {context.command}")

    @staticmethod
    def _completed_output(
        command: str,
        result_payload: dict[str, Any],
    ) -> CommandOutput:
        items = result_payload.get("items")
        if not isinstance(items, list):
            items = result_payload.get("candidates", [])

        return CommandOutput(
            status=str(result_payload.get("status", "ok")),
            result_type=command,
            items=items if isinstance(items, list) else [],
            meta={"reused_result": True},
            result_payload=result_payload,
        )

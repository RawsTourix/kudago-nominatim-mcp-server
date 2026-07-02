from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.api.deps import ArqPool, DbSession
from app.models.job import Job
from app.repositories.job_repository import JobRepository
from app.repositories.result_repository import ResultRepository
from app.repositories.upstream_call_repository import UpstreamCallRepository
from app.schemas.jobs import (
    CommandResultResponse,
    JobCreateRequest,
    JobCreateResponse,
    JobEventResponse,
    JobEventsResponse,
    JobGetResponse,
    JobResponse,
    JobResultsResponse,
    JobRunResponse,
    JobEnqueueResponse,
    JobUpstreamCallsResponse,
    UpstreamCallResponse,
)
from app.services.job_service import JobService
from app.services.queue_service import QueueService


router = APIRouter(prefix="/jobs", tags=["jobs"])


def compact_result_payload(
    payload: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if payload is None:
        return None

    if not isinstance(payload, dict):
        return payload

    if "items" not in payload or not isinstance(payload["items"], list):
        return payload

    compact = dict(payload)
    items = compact.pop("items")
    compact["items_hidden"] = True
    compact["items_count"] = len(items)
    compact["items_hint"] = (
        "Use /api/v1/jobs/{job_id}/results to fetch stored result items."
    )
    return compact


def to_job_response(job: Job, *, include_result: bool = False) -> JobResponse:
    result_payload = (
        job.result_payload
        if include_result
        else compact_result_payload(job.result_payload)
    )

    return JobResponse(
        id=job.id,
        command=job.command,
        status=job.status,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        input_payload=job.input_payload,
        result_payload=result_payload,
        error_type=job.error_type,
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


@router.post("", response_model=JobCreateResponse)
async def create_job(payload: JobCreateRequest, session: DbSession):
    service = JobService(session)

    job = await service.create_job_from_api_request(
        endpoint="/api/v1/jobs",
        method="POST",
        command=payload.command,
        input_payload=payload.input_payload,
    )

    await session.commit()

    return JobCreateResponse(
        status="ok",
        job_id=job.id,
    )

@router.get("/{job_id}", response_model=JobGetResponse)
async def get_job(
    job_id: UUID,
    session: DbSession,
    include_result: bool = False,
):
    repo = JobRepository(session)
    job = await repo.get_by_id(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobGetResponse(
        status="ok",
        job=to_job_response(job, include_result=include_result),
    )


@router.post("/{job_id}/run-test", response_model=JobRunResponse)
async def run_test_job(job_id: UUID, session: DbSession):
    service = JobService(session)
    job = await service.run_test_job(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    await session.commit()

    return JobRunResponse(
        status="ok",
        job=to_job_response(job),
    )


@router.get("/{job_id}/events", response_model=JobEventsResponse)
async def get_job_events(job_id: UUID, session: DbSession):
    repo = JobRepository(session)
    job = await repo.get_by_id(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    events = await repo.get_events(job_id)

    return JobEventsResponse(
        status="ok",
        events=[
            JobEventResponse(
                id=event.id,
                job_id=event.job_id,
                event_type=event.event_type,
                message=event.message,
                data=event.data,
                created_at=event.created_at,
            )
            for event in events
        ],
    )


@router.get("/{job_id}/results", response_model=JobResultsResponse)
async def get_job_results(job_id: UUID, session: DbSession):
    job_repo = JobRepository(session)
    result_repo = ResultRepository(session)
    job = await job_repo.get_by_id(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    results = await result_repo.get_by_job_id(job_id)

    return JobResultsResponse(
        status="ok",
        results=[
            CommandResultResponse(
                id=result.id,
                job_id=result.job_id,
                result_type=result.result_type,
                items=result.items,
                meta=result.meta,
                created_at=result.created_at,
            )
            for result in results
        ],
    )


@router.get("/{job_id}/upstream-calls", response_model=JobUpstreamCallsResponse)
async def get_job_upstream_calls(job_id: UUID, session: DbSession):
    job_repo = JobRepository(session)
    upstream_repo = UpstreamCallRepository(session)
    job = await job_repo.get_by_id(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    calls = await upstream_repo.get_by_job_id(job_id)

    return JobUpstreamCallsResponse(
        status="ok",
        upstream_calls=[
            UpstreamCallResponse(
                id=call.id,
                job_id=call.job_id,
                provider=call.provider,
                operation=call.operation,
                url_path=call.url_path,
                request_payload=call.request_payload,
                response_payload=call.response_payload,
                response_status_code=call.response_status_code,
                duration_ms=call.duration_ms,
                success=call.success,
                error_type=call.error_type,
                error_message=call.error_message,
                created_at=call.created_at,
            )
            for call in calls
        ],
    )


@router.post("/{job_id}/enqueue-test", response_model=JobEnqueueResponse)
async def enqueue_test_job(job_id: UUID, session: DbSession, redis: ArqPool):
    job_repo = JobRepository(session)
    job = await job_repo.get_by_id(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status == "succeeded":
        return JobEnqueueResponse(
            status="ok",
            job_id=job.id,
            queue_job_id=job.queue_job_id,
            enqueued=False,
        )

    queue_service = QueueService(redis)
    queue_job_id = await queue_service.enqueue_test_job(job_id)

    service = JobService(session)
    job = await service.mark_enqueued(
        job_id=job_id,
        queue_job_id=queue_job_id,
    )

    await session.commit()

    return JobEnqueueResponse(
        status="ok",
        job_id=job_id,
        queue_job_id=queue_job_id,
        enqueued=queue_job_id is not None,
    )

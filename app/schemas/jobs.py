from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class JobCreateRequest(BaseModel):
    command: str = Field(min_length=1, max_length=100)
    input_payload: dict[str, Any] = Field(default_factory=dict)


class JobCreateResponse(BaseModel):
    status: str
    job_id: UUID


class JobResponse(BaseModel):
    id: UUID
    command: str
    status: str
    attempts: int
    max_attempts: int
    input_payload: dict[str, Any]
    result_payload: dict[str, Any] | None
    error_type: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class JobGetResponse(BaseModel):
    status: str
    job: JobResponse


class JobRunResponse(BaseModel):
    status: str
    job: JobResponse


class JobEventResponse(BaseModel):
    id: int
    job_id: UUID
    event_type: str
    message: str | None
    data: dict[str, Any] | None
    created_at: datetime


class JobEventsResponse(BaseModel):
    status: str
    events: list[JobEventResponse]


class CommandResultResponse(BaseModel):
    id: UUID
    job_id: UUID
    result_type: str
    items: list[dict[str, Any]]
    meta: dict[str, Any]
    created_at: datetime


class JobResultsResponse(BaseModel):
    status: str
    results: list[CommandResultResponse]


class JobEnqueueResponse(BaseModel):
    status: str
    job_id: UUID
    queue_job_id: str | None
    enqueued: bool
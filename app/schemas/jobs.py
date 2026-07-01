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
from uuid import UUID

from pydantic import BaseModel, Field


class GeoResolveRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    countrycodes: str | None = "ru"
    limit: int = Field(default=5, ge=1, le=10)
    accept_language: str | None = "ru"


class GeoResolveQueuedResponse(BaseModel):
    status: str
    job_id: UUID
    queue_job_id: str | None
    enqueued: bool

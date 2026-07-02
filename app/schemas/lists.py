from uuid import UUID

from pydantic import BaseModel, Field


class ListsSearchRequest(BaseModel):
    location: str | None = Field(default=None, max_length=100)
    place_query: str | None = Field(default=None, max_length=500)

    tags: str | None = None

    page: int = Field(default=1, ge=1, le=10_000)
    page_size: int = Field(default=10, ge=1, le=100)
    lang: str | None = "ru"


class ListsSearchQueuedResponse(BaseModel):
    status: str
    job_id: UUID
    queue_job_id: str | None
    enqueued: bool

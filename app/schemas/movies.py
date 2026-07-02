from uuid import UUID

from pydantic import BaseModel, Field


class MoviesSearchRequest(BaseModel):
    location: str | None = Field(default=None, max_length=100)
    place_query: str | None = Field(default=None, max_length=500)

    place_id: int | None = Field(default=None, ge=1)

    tags: str | None = None
    is_free: bool | None = None
    premiering_in_location: bool | None = None

    actual_since: str | int | None = None
    actual_until: str | int | None = None
    include_past: bool = False

    page: int = Field(default=1, ge=1, le=10_000)
    page_size: int = Field(default=10, ge=1, le=100)
    lang: str | None = "ru"


class MoviesSearchQueuedResponse(BaseModel):
    status: str
    job_id: UUID
    queue_job_id: str | None
    enqueued: bool

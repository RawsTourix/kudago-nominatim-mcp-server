from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class MovieShowingsSearchRequest(BaseModel):
    location: str | None = Field(default=None, max_length=100)
    place_query: str | None = Field(default=None, max_length=500)

    movie_id: int | None = Field(default=None, ge=1)
    place_id: int | None = Field(default=None, ge=1)

    actual_since: str | int | None = None
    actual_until: str | int | None = None

    is_free: bool | None = None

    page: int = Field(default=1, ge=1, le=10_000)
    page_size: int = Field(default=10, ge=1, le=100)
    lang: str | None = "ru"

    @model_validator(mode="after")
    def validate_time_window(self):
        has_since = self.actual_since is not None
        has_until = self.actual_until is not None

        if has_since != has_until:
            raise ValueError("actual_since and actual_until must be provided together")

        return self


class MovieShowingsSearchQueuedResponse(BaseModel):
    status: str
    job_id: UUID
    queue_job_id: str | None
    enqueued: bool

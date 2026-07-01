from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class EventsSearchRequest(BaseModel):
    location: str | None = Field(default=None, max_length=100)
    place_query: str | None = Field(default=None, max_length=500)

    lat: float | None = None
    lon: float | None = None
    radius: int | None = Field(default=None, ge=100, le=100_000)

    actual_since: str | int | None = None
    actual_until: str | int | None = None

    categories: str | None = None
    tags: str | None = None
    is_free: bool | None = None

    page: int = Field(default=1, ge=1, le=10_000)
    page_size: int = Field(default=10, ge=1, le=100)
    lang: str | None = "ru"

    @model_validator(mode="after")
    def validate_coordinates(self):
        has_any_geo = (
            self.lat is not None or self.lon is not None or self.radius is not None
        )
        has_all_geo = (
            self.lat is not None and self.lon is not None and self.radius is not None
        )

        if has_any_geo and not has_all_geo:
            raise ValueError("lat, lon and radius must be provided together")

        return self


class EventsSearchQueuedResponse(BaseModel):
    status: str
    job_id: UUID
    queue_job_id: str | None
    enqueued: bool


class EventsSearchResultMeta(BaseModel):
    status: str
    source: str
    geo: dict[str, Any] | None = None
    count: int | None = None
    returned: int | None = None

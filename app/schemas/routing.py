from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class StreetRouteProfile(StrEnum):
    WALKING = "walking"
    CYCLING = "cycling"
    DRIVING = "driving"


class TransitMode(StrEnum):
    TRANSIT = "TRANSIT"
    TRAM = "TRAM"
    SUBWAY = "SUBWAY"
    FERRY = "FERRY"
    BUS = "BUS"
    COACH = "COACH"
    RAIL = "RAIL"
    HIGHSPEED_RAIL = "HIGHSPEED_RAIL"
    LONG_DISTANCE = "LONG_DISTANCE"
    NIGHT_RAIL = "NIGHT_RAIL"
    REGIONAL_RAIL = "REGIONAL_RAIL"
    SUBURBAN = "SUBURBAN"
    FUNICULAR = "FUNICULAR"
    AERIAL_LIFT = "AERIAL_LIFT"


class TransitRouteRequest(BaseModel):
    origin_lat: float = Field(ge=-90, le=90)
    origin_lon: float = Field(ge=-180, le=180)
    destination_lat: float = Field(ge=-90, le=90)
    destination_lon: float = Field(ge=-180, le=180)

    time: datetime | None = None
    arrive_by: bool = False

    transit_modes: list[TransitMode] | None = None
    max_transfers: int | None = Field(default=None, ge=0, le=10)
    max_travel_time_minutes: int | None = Field(default=None, ge=1, le=1440)
    min_transfer_time_minutes: int | None = Field(default=None, ge=0, le=120)

    num_itineraries: int = Field(default=3, ge=1, le=5)
    search_window_seconds: int = Field(default=900, ge=0, le=7200)
    language: str | None = Field(default="ru", max_length=20)

    @field_validator("time")
    @classmethod
    def validate_aware_time(cls, value: datetime | None) -> datetime | None:
        if value is not None and (
            value.tzinfo is None or value.utcoffset() is None
        ):
            raise ValueError("time must include a timezone or UTC offset")
        return value

    @field_validator("transit_modes")
    @classmethod
    def validate_transit_modes(
        cls,
        value: list[TransitMode] | None,
    ) -> list[TransitMode] | None:
        if value is None:
            return None
        if not value:
            raise ValueError("transit_modes must not be empty")

        unique = list(dict.fromkeys(value))
        if TransitMode.TRANSIT in unique and unique != [TransitMode.TRANSIT]:
            raise ValueError(
                "TRANSIT cannot be combined with specific transit modes"
            )
        return unique

    @model_validator(mode="after")
    def validate_route_request(self):
        if (
            self.origin_lat == self.destination_lat
            and self.origin_lon == self.destination_lon
        ):
            raise ValueError("origin and destination must be different")
        if self.arrive_by and self.time is None:
            raise ValueError("time is required when arrive_by is true")
        return self


class StreetRouteRequest(BaseModel):
    origin_lat: float = Field(ge=-90, le=90)
    origin_lon: float = Field(ge=-180, le=180)
    destination_lat: float = Field(ge=-90, le=90)
    destination_lon: float = Field(ge=-180, le=180)

    profile: StreetRouteProfile = StreetRouteProfile.WALKING
    language: str | None = Field(default="ru", max_length=20)
    include_instructions: bool = True
    include_geometry: bool = False

    @model_validator(mode="after")
    def validate_distinct_points(self):
        if (
            self.origin_lat == self.destination_lat
            and self.origin_lon == self.destination_lon
        ):
            raise ValueError("origin and destination must be different")
        return self


class RoutingQueuedResponse(BaseModel):
    status: str
    job_id: UUID
    queue_job_id: str | None
    enqueued: bool

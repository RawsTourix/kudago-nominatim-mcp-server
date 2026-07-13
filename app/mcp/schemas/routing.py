from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator

from app.mcp.schemas.common import Coordinates


class PublicTransportMode(StrEnum):
    TRAM = "tram"
    SUBWAY = "subway"
    FERRY = "ferry"
    BUS = "bus"
    COACH = "coach"
    RAIL = "rail"
    HIGH_SPEED_RAIL = "high_speed_rail"
    LONG_DISTANCE_RAIL = "long_distance_rail"
    NIGHT_RAIL = "night_rail"
    REGIONAL_RAIL = "regional_rail"
    SUBURBAN_RAIL = "suburban_rail"
    FUNICULAR = "funicular"
    AERIAL_LIFT = "aerial_lift"


class StreetTravelMode(StrEnum):
    WALKING = "walking"
    CYCLING = "cycling"
    DRIVING = "driving"


OriginInput = Annotated[
    Coordinates,
    Field(
        description="Route origin as latitude then longitude in decimal degrees."
    ),
]
DestinationInput = Annotated[
    Coordinates,
    Field(
        description=(
            "Route destination as latitude then longitude in decimal degrees; "
            "it must differ from origin."
        )
    ),
]
DepartureTimeInput = Annotated[
    datetime | None,
    Field(
        description=(
            "Timezone-aware ISO 8601 earliest departure time. Do not combine "
            "with arrival_time; when both are omitted, current time is used."
        )
    ),
]
ArrivalTimeInput = Annotated[
    datetime | None,
    Field(
        description=(
            "Timezone-aware ISO 8601 latest arrival time. Do not combine with "
            "departure_time."
        )
    ),
]
PublicTransportModesInput = Annotated[
    list[PublicTransportMode] | None,
    Field(
        description=(
            "Optional allowed public-transport modes. Common values are tram, "
            "subway, bus and rail; the complete list is in this field's enum. "
            "Null lets the server use its safe public-transport default set."
        ),
        min_length=1,
    ),
]
MaxTransfersInput = Annotated[
    int | None,
    Field(
        description=(
            "Optional maximum number of interchanges between transit legs; "
            "walking access and egress do not count. Range 0 to 10."
        ),
        ge=0,
        le=10,
    ),
]
RouteLimitInput = Annotated[
    int,
    Field(
        description="Maximum route alternatives to request; 1 to 5, default 3.",
        ge=1,
        le=5,
    ),
]
StreetModeInput = Annotated[
    StreetTravelMode,
    Field(
        description=(
            "Independent street travel mode: walking, cycling or driving. "
            "Public transport is not supported by this tool."
        )
    ),
]


class PlanPublicTransportInput(BaseModel):
    origin: OriginInput
    destination: DestinationInput
    departure_time: DepartureTimeInput = None
    arrival_time: ArrivalTimeInput = None
    modes: PublicTransportModesInput = None
    max_transfers: MaxTransfersInput = None
    limit: RouteLimitInput = 3

    @field_validator("departure_time", "arrival_time")
    @classmethod
    def validate_aware_time(cls, value: datetime | None) -> datetime | None:
        if value is not None and (
            value.tzinfo is None or value.utcoffset() is None
        ):
            raise ValueError("routing datetime must include a timezone or UTC offset")
        return value

    @model_validator(mode="after")
    def validate_route(self):
        if self.departure_time is not None and self.arrival_time is not None:
            raise ValueError(
                "departure_time and arrival_time cannot be provided together."
            )
        if self.origin == self.destination:
            raise ValueError("origin and destination must be different.")
        if self.modes is not None:
            self.modes = list(dict.fromkeys(self.modes))
        return self


class PlanStreetRouteInput(BaseModel):
    origin: OriginInput
    destination: DestinationInput
    mode: StreetModeInput = StreetTravelMode.WALKING

    @model_validator(mode="after")
    def validate_distinct_points(self):
        if self.origin == self.destination:
            raise ValueError("origin and destination must be different.")
        return self


__all__ = [
    "ArrivalTimeInput",
    "DepartureTimeInput",
    "DestinationInput",
    "MaxTransfersInput",
    "OriginInput",
    "PlanPublicTransportInput",
    "PlanStreetRouteInput",
    "PublicTransportMode",
    "PublicTransportModesInput",
    "RouteLimitInput",
    "StreetModeInput",
    "StreetTravelMode",
]

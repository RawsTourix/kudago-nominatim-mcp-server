from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator

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


class RoutePoint(BaseModel):
    latitude: float = Field(
        ge=-90,
        le=90,
        description=(
            "Latitude in decimal degrees from the same selected location "
            "candidate as longitude."
        ),
    )
    longitude: float = Field(
        ge=-180,
        le=180,
        description=(
            "Longitude in decimal degrees from the same selected location "
            "candidate as latitude."
        ),
    )
    label: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description=(
            "Optional human-readable name of this exact coordinate point. "
            "Examples: 'станция Нахабино', "
            "'Музей-усадьба Архангельское'. "
            "The label does not affect routing."
        ),
    )


OriginInput = Annotated[
    RoutePoint,
    Field(
        description="Route origin as latitude then longitude in decimal degrees."
    ),
]
DestinationInput = Annotated[
    RoutePoint,
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
            "Timezone-aware ISO 8601 earliest departure time. Use when the "
            "journey must leave at or after this moment. Do not combine with "
            "arrival_time."
        )
    ),
]
ArrivalTimeInput = Annotated[
    datetime | None,
    Field(
        description=(
            "Timezone-aware ISO 8601 latest arrival time. Use when the user "
            "must reach an event before it starts. Do not combine with "
            "departure_time."
        )
    ),
]
PublicTransportModesInput = Annotated[
    list[PublicTransportMode] | None,
    Field(
        description=(
            "Optional explicit restrictions on public-transport modes accepted "
            "by this MCP facade. Omit the field to allow every transit mode "
            "supported by the provider. The complete list of values accepted "
            "by this field is in its enum. Meanings: tram — tram; subway — "
            "metro/subway; ferry — scheduled ferry; bus — short-distance/local "
            "bus; coach — long-distance coach; rail — aggregate rail "
            "restriction including high-speed, long-distance, night, regional, "
            "suburban and subway; high_speed_rail — high-speed long-distance "
            "train; long_distance_rail — intercity long-distance train; "
            "night_rail — night train; regional_rail — regional train; "
            "suburban_rail — suburban/commuter train; funicular — funicular; "
            "aerial_lift — suspended cable transport."
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
MaxRoutesInput = Annotated[
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
            "Independent street travel mode: walking — pedestrian route; "
            "cycling — regular bicycle route; driving — passenger-car route. "
            "Public transport is not supported by this tool."
        )
    ),
]


class PlanPublicTransportInput(BaseModel):
    origin: OriginInput
    destination: DestinationInput
    departure_time: DepartureTimeInput = None
    arrival_time: ArrivalTimeInput = None
    transport_modes: PublicTransportModesInput = None
    max_transfers: MaxTransfersInput = None
    max_routes: MaxRoutesInput = 3

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
        if (self.departure_time is None) == (self.arrival_time is None):
            raise ValueError(
                "Provide exactly one of departure_time or arrival_time."
            )
        if _same_point(self.origin, self.destination):
            raise ValueError("origin and destination must be different.")
        if self.transport_modes is not None:
            self.transport_modes = list(dict.fromkeys(self.transport_modes))
        return self


class PlanStreetRouteInput(BaseModel):
    origin: OriginInput
    destination: DestinationInput
    travel_mode: StreetModeInput = StreetTravelMode.WALKING

    @model_validator(mode="after")
    def validate_distinct_points(self):
        if _same_point(self.origin, self.destination):
            raise ValueError("origin and destination must be different.")
        return self


def _same_point(origin: RoutePoint, destination: RoutePoint) -> bool:
    return (
        origin.latitude == destination.latitude
        and origin.longitude == destination.longitude
    )


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
    "MaxRoutesInput",
    "RoutePoint",
    "StreetModeInput",
    "StreetTravelMode",
]

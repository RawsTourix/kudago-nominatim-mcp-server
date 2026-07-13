from __future__ import annotations

import re
from datetime import date
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator

from app.mcp.reference_data import KudaGoLocationSlug, reference_timezone


class Coordinates(BaseModel):
    latitude: float = Field(
        ge=-90,
        le=90,
        description=(
            "Latitude in decimal degrees, written first in this object; "
            "valid range is -90 to 90."
        ),
    )
    longitude: float = Field(
        ge=-180,
        le=180,
        description=(
            "Longitude in decimal degrees, written second in this object; "
            "valid range is -180 to 180."
        ),
    )


PlaceInput = Annotated[
    str | None,
    Field(
        description=(
            "Free-form city, district, address, station, landmark or venue name. "
            "Provide exactly one of place, location_slug or coordinates."
        ),
        min_length=1,
        max_length=500,
    ),
]
CityInput = Annotated[
    str | None,
    Field(
        description=(
            "Ordinary city name that the server will match to a supported "
            "KudaGo location. Provide exactly one of city or location_slug; "
            "this is not an arbitrary street address."
        ),
        min_length=1,
        max_length=500,
    ),
]
LocationSlugInput = Annotated[
    KudaGoLocationSlug | None,
    Field(
        description=(
            "Exact KudaGo location slug from the committed v1.4 reference "
            "snapshot enum. Common values include msk, spb and ekb; the "
            "complete committed list is in this field's enum. Do not combine "
            "it with a free-form location field."
        )
    ),
]
CoordinatesInput = Annotated[
    Coordinates | None,
    Field(
        description=(
            "Exact geographic point as latitude then longitude. Provide exactly "
            "one location source and include radius_km with coordinates."
        )
    ),
]
RadiusKmInput = Annotated[
    float | None,
    Field(
        description=(
            "Search radius in kilometres, from 0.1 to 100. Required with "
            "coordinates and forbidden without coordinates."
        ),
        ge=0.1,
        le=100,
    ),
]
PageInput = Annotated[
    int,
    Field(
        description="One-based result page number; defaults to 1.",
        ge=1,
        le=10_000,
    ),
]
SearchLimitInput = Annotated[
    int,
    Field(
        description=(
            "Maximum number of results requested for this page, from 1 to 20; "
            "defaults to 10 and is mapped to the upstream page size."
        ),
        ge=1,
        le=20,
    ),
]
CalendarDateInput = Annotated[
    date | None,
    Field(
        description=(
            "Single calendar date in YYYY-MM-DD format. Do not combine with "
            "date_from or date_to."
        )
    ),
]
DateFromInput = Annotated[
    date | None,
    Field(
        description=(
            "First calendar date in an inclusive YYYY-MM-DD range. Provide it "
            "together with date_to and do not combine with date."
        )
    ),
]
DateToInput = Annotated[
    date | None,
    Field(
        description=(
            "Last calendar date in an inclusive YYYY-MM-DD range of at most "
            "31 days. Provide it together with date_from."
        )
    ),
]
TimezoneInput = Annotated[
    str | None,
    Field(
        description=(
            "Timezone used to convert calendar-day boundaries to UTC. Use an "
            "IANA name such as Europe/Moscow or a fixed offset such as +03:00. "
            "When omitted, an exact location_slug or supported city name uses "
            "the committed KudaGo timezone; otherwise timezone is required."
        ),
        min_length=1,
        max_length=64,
    ),
]


class LocationSourceModel(BaseModel):
    place: PlaceInput = None
    location_slug: LocationSlugInput = None
    coordinates: CoordinatesInput = None
    radius_km: RadiusKmInput = None

    @model_validator(mode="after")
    def validate_location_source(self):
        sources = [
            self.place is not None,
            self.location_slug is not None,
            self.coordinates is not None,
        ]
        if sum(sources) != 1:
            raise ValueError(
                "Provide exactly one of place, location_slug or coordinates."
            )
        if self.coordinates is not None and self.radius_km is None:
            raise ValueError(
                "radius_km is required when coordinates are provided."
            )
        if self.coordinates is None and self.radius_km is not None:
            raise ValueError("radius_km requires coordinates.")
        return self


class CitySourceModel(BaseModel):
    city: CityInput = None
    location_slug: LocationSlugInput = None

    @model_validator(mode="after")
    def validate_city_source(self):
        if (self.city is None) == (self.location_slug is None):
            raise ValueError("Provide exactly one of city or location_slug.")
        return self


class CalendarWindowModel(BaseModel):
    date: CalendarDateInput = None
    date_from: DateFromInput = None
    date_to: DateToInput = None
    timezone: TimezoneInput = None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if _fixed_offset(value) is not None:
            return value
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(
                "timezone must be an IANA timezone or a fixed UTC offset"
            ) from exc
        return value

    @model_validator(mode="after")
    def validate_window(self):
        has_range_value = self.date_from is not None or self.date_to is not None
        if self.date is not None and has_range_value:
            raise ValueError("date cannot be combined with date_from/date_to.")
        if (self.date_from is None) != (self.date_to is None):
            raise ValueError("date_from and date_to must be provided together.")
        if self.date_from is not None and self.date_to is not None:
            if self.date_to < self.date_from:
                raise ValueError("date_to must not be earlier than date_from.")
            if (self.date_to - self.date_from).days + 1 > 31:
                raise ValueError("The calendar date range must not exceed 31 days.")
        if self.has_window and self.timezone is None:
            source_fields = (
                "place",
                "city",
                "location_slug",
                "coordinates",
            )
            available_source_fields = [
                field for field in source_fields if hasattr(self, field)
            ]
            if available_source_fields and sum(
                getattr(self, field, None) is not None
                for field in available_source_fields
            ) != 1:
                return self
            if hasattr(self, "radius_km") and (
                (getattr(self, "coordinates", None) is not None)
                != (getattr(self, "radius_km", None) is not None)
            ):
                return self
            inferred_timezone = reference_timezone(
                location_slug=getattr(self, "location_slug", None),
                location_text=(
                    getattr(self, "city", None) or getattr(self, "place", None)
                ),
            )
            if inferred_timezone is None:
                raise ValueError(
                    "timezone is required for coordinates or a free-form "
                    "location that does not exactly match the KudaGo snapshot."
                )
        return self

    @property
    def has_window(self) -> bool:
        return self.date is not None or self.date_from is not None


def _fixed_offset(value: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"([+-])(\d{2}):(\d{2})", value)
    if match is None:
        return None
    hours = int(match.group(2))
    minutes = int(match.group(3))
    if hours > 23 or minutes > 59:
        return None
    sign = 1 if match.group(1) == "+" else -1
    return sign * hours, sign * minutes


__all__ = [
    "CalendarDateInput",
    "CalendarWindowModel",
    "CityInput",
    "CitySourceModel",
    "Coordinates",
    "CoordinatesInput",
    "DateFromInput",
    "DateToInput",
    "LocationSlugInput",
    "LocationSourceModel",
    "PageInput",
    "PlaceInput",
    "RadiusKmInput",
    "SearchLimitInput",
    "TimezoneInput",
]

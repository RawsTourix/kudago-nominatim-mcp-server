from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator

from app.mcp.reference_data import EventCategory, PlaceCategory
from app.mcp.schemas.common import (
    CalendarWindowModel,
    CitySourceModel,
    LocationSourceModel,
    PageInput,
    SearchLimitInput,
)


CountryCode = Annotated[
    str,
    Field(
        pattern=r"^[a-zA-Z]{2}$",
        description="ISO 3166-1 alpha-2 country code, for example ru or de.",
    ),
]
ResolvePlaceInput = Annotated[
    str,
    Field(
        description=(
            "Free-form city, district, address, station, landmark or object to "
            "geocode, for example 'станция Нахабино'."
        ),
        min_length=1,
        max_length=500,
    ),
]
CountryCodesInput = Annotated[
    list[CountryCode] | None,
    Field(
        description=(
            "Optional list of up to 10 ISO 3166-1 alpha-2 country filters. Null "
            "means international search without a country restriction."
        ),
        max_length=10,
    ),
]
LanguageInput = Annotated[
    str,
    Field(
        description=(
            "Preferred Nominatim result language as an Accept-Language value, "
            "for example ru or ru,en;q=0.8; defaults to ru."
        ),
        min_length=1,
        max_length=100,
    ),
]
ResolveLimitInput = Annotated[
    int,
    Field(
        description=(
            "Maximum coordinate candidates to return; 1 to 10, default 5. "
            "The MCP limit is intentionally below the Nominatim maximum."
        ),
        ge=1,
        le=10,
    ),
]
EventCategoriesInput = Annotated[
    list[EventCategory] | None,
    Field(
        description=(
            "KudaGo event categories, not place categories. Common values are "
            "concert, exhibition, theater, festival and tour; the complete "
            "committed v1.4 snapshot is in this field's enum."
        ),
        min_length=1,
    ),
]
PlaceCategoriesInput = Annotated[
    list[PlaceCategory] | None,
    Field(
        description=(
            "KudaGo venue and attraction categories, not event categories. "
            "Common values include museums, theatre, park, restaurants and "
            "clubs; the complete committed v1.4 snapshot is in this field's enum."
        ),
        min_length=1,
    ),
]
OptionalBoolInput = Annotated[
    bool | None,
    Field(
        description=(
            "Optional boolean filter. Null leaves this criterion unspecified; "
            "true and false are passed explicitly."
        )
    ),
]
OnlyCurrentInput = Annotated[
    bool,
    Field(
        description=(
            "When true, return only currently relevant city news; defaults to true."
        )
    ),
]


class ResolveLocationInput(BaseModel):
    place: ResolvePlaceInput
    country_codes: CountryCodesInput = None
    language: LanguageInput = "ru"
    limit: ResolveLimitInput = 5

    @field_validator("country_codes")
    @classmethod
    def normalize_country_codes(
        cls,
        value: list[str] | None,
    ) -> list[str] | None:
        if not value:
            return None
        return list(dict.fromkeys(item.lower() for item in value))


class FindEventsInput(LocationSourceModel, CalendarWindowModel):
    categories: EventCategoriesInput = None
    free_only: OptionalBoolInput = None
    page: PageInput = 1
    limit: SearchLimitInput = 10

    @model_validator(mode="after")
    def require_time_window(self):
        if not self.has_window:
            raise ValueError(
                "Provide date or a complete date_from/date_to range for events."
            )
        return self


class FindPlacesInput(LocationSourceModel):
    categories: PlaceCategoriesInput = None
    page: PageInput = 1
    limit: SearchLimitInput = 10


class FindCityNewsInput(CitySourceModel):
    only_current: OnlyCurrentInput = True
    page: PageInput = 1
    limit: SearchLimitInput = 10


class FindCityGuidesInput(CitySourceModel):
    page: PageInput = 1
    limit: SearchLimitInput = 10


__all__ = [
    "CountryCodesInput",
    "EventCategoriesInput",
    "FindCityGuidesInput",
    "FindCityNewsInput",
    "FindEventsInput",
    "FindPlacesInput",
    "LanguageInput",
    "OnlyCurrentInput",
    "OptionalBoolInput",
    "PlaceCategoriesInput",
    "ResolveLimitInput",
    "ResolveLocationInput",
    "ResolvePlaceInput",
]

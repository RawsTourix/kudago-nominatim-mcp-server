from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import Field

from app.mcp.schemas.common import (
    CalendarWindowModel,
    CitySourceModel,
    PageInput,
    SearchLimitInput,
)
from app.mcp.schemas.discovery import OptionalBoolInput


CinemaIdInput = Annotated[
    int | None,
    Field(
        description=(
            "Optional KudaGo cinema/place identifier used to narrow results; "
            "minimum value is 1."
        ),
        ge=1,
    ),
]
MovieIdInput = Annotated[
    int | None,
    Field(
        description=(
            "Optional KudaGo movie identifier used to narrow actual showings; "
            "minimum value is 1."
        ),
        ge=1,
    ),
]
PremieringOnlyInput = Annotated[
    bool | None,
    Field(
        description=(
            "When true, restrict movies to premieres in the selected KudaGo "
            "location. Null leaves the criterion unspecified."
        )
    ),
]
ShowingCalendarDateInput = Annotated[
    date | None,
    Field(
        description=(
            "Single showing date in YYYY-MM-DD format. Do not combine with "
            "date_from/date_to. When all date fields are omitted, the next "
            "seven days are searched."
        )
    ),
]
ShowingDateFromInput = Annotated[
    date | None,
    Field(
        description=(
            "First showing date in an inclusive YYYY-MM-DD range. Provide it "
            "with date_to; omitting the entire date window searches the next "
            "seven days."
        )
    ),
]
ShowingDateToInput = Annotated[
    date | None,
    Field(
        description=(
            "Last showing date in an inclusive range of at most 31 days. "
            "Provide it with date_from; omitting all dates searches the next "
            "seven days."
        )
    ),
]


class FindMoviesInput(CitySourceModel, CalendarWindowModel):
    cinema_id: CinemaIdInput = None
    free_only: OptionalBoolInput = None
    premiering_only: PremieringOnlyInput = None
    page: PageInput = 1
    limit: SearchLimitInput = 10


class FindMovieShowingsInput(CitySourceModel, CalendarWindowModel):
    movie_id: MovieIdInput = None
    cinema_id: CinemaIdInput = None
    free_only: OptionalBoolInput = None
    page: PageInput = 1
    limit: SearchLimitInput = 10


__all__ = [
    "CinemaIdInput",
    "FindMovieShowingsInput",
    "FindMoviesInput",
    "MovieIdInput",
    "PremieringOnlyInput",
    "ShowingCalendarDateInput",
    "ShowingDateFromInput",
    "ShowingDateToInput",
]

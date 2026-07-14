from __future__ import annotations

from functools import partial
from typing import Any

from fastmcp import Context, FastMCP
from pydantic import ValidationError

from app.mcp.executor import run_mcp_command
from app.mcp.mappers import (
    city_payload,
    resolve_calendar_timezone,
    to_utc_window,
)
from app.mcp.schemas.cinema import (
    CinemaIdInput,
    FindMovieShowingsInput,
    FindMoviesInput,
    MovieIdInput,
    PremieringOnlyInput,
    ShowingCalendarDateInput,
    ShowingDateFromInput,
    ShowingDateToInput,
)
from app.mcp.schemas.common import (
    CalendarDateInput,
    CityInput,
    DateFromInput,
    DateToInput,
    LocationSlugInput,
    PageInput,
    SearchLimitInput,
    TimezoneInput,
)
from app.mcp.schemas.discovery import OptionalBoolInput
from app.mcp.serializers import serialize_movie_showings, serialize_movies
from app.mcp.tools._common import (
    MCP_FACADE_VERSION,
    READ_ONLY_TOOL_ANNOTATIONS,
    agent_filters,
    validation_error,
)
from app.schemas.movie_showings import MovieShowingsSearchRequest
from app.schemas.movies import MoviesSearchRequest


def register_cinema_tools(mcp: FastMCP) -> None:
    @mcp.tool(
        name="find_movies",
        annotations=READ_ONLY_TOOL_ANNOTATIONS,
        version=MCP_FACADE_VERSION,
    )
    async def find_movies(
        ctx: Context,
        city: CityInput = None,
        location_slug: LocationSlugInput = None,
        cinema_id: CinemaIdInput = None,
        date: CalendarDateInput = None,
        date_from: DateFromInput = None,
        date_to: DateToInput = None,
        timezone: TimezoneInput = None,
        free_only: OptionalBoolInput = None,
        premiering_only: PremieringOnlyInput = None,
        page: PageInput = 1,
        limit: SearchLimitInput = 10,
    ) -> dict[str, Any]:
        """Find KudaGo movie records available for a city, cinema or date range.

        This tool returns movies, not exact screening times. Use find_movie_showings when the user needs a cinema, time or showing-level price information.
        """
        tool_name = "find_movies"
        try:
            agent_request = FindMoviesInput(
                city=city,
                location_slug=location_slug,
                cinema_id=cinema_id,
                date=date,
                date_from=date_from,
                date_to=date_to,
                timezone=timezone,
                free_only=free_only,
                premiering_only=premiering_only,
                page=page,
                limit=limit,
            )
            applied_timezone = (
                resolve_calendar_timezone(
                    timezone_name=agent_request.timezone,
                    location_slug=agent_request.location_slug,
                    location_text=agent_request.city,
                )
                if agent_request.has_window
                else None
            )
            actual_since, actual_until = to_utc_window(
                single_date=agent_request.date,
                date_from=agent_request.date_from,
                date_to=agent_request.date_to,
                timezone_name=applied_timezone,
            )
            request = MoviesSearchRequest(
                **city_payload(
                    city=agent_request.city,
                    location_slug=agent_request.location_slug,
                ),
                place_id=agent_request.cinema_id,
                is_free=agent_request.free_only,
                premiering_in_location=agent_request.premiering_only,
                actual_since=actual_since,
                actual_until=actual_until,
                include_past=actual_since is not None,
                page=agent_request.page,
                page_size=agent_request.limit,
                lang="ru",
            )
        except ValidationError as exc:
            return validation_error(tool_name, exc)

        return await run_mcp_command(
            redis=ctx.lifespan_context["arq_redis"],
            tool_name=tool_name,
            endpoint="mcp://tools/find_movies",
            command="movies.search",
            payload=request.model_dump(),
            request_text=agent_request.city or agent_request.location_slug.value,
            data_factory=partial(
                serialize_movies,
                actual_since=actual_since,
                actual_until=actual_until,
                applied_timezone=applied_timezone,
                applied_filters=agent_filters(
                    city=agent_request.city,
                    location_slug=agent_request.location_slug,
                    cinema_id=agent_request.cinema_id,
                    date=agent_request.date,
                    date_from=agent_request.date_from,
                    date_to=agent_request.date_to,
                    timezone=applied_timezone,
                    free_only=agent_request.free_only,
                    premiering_only=agent_request.premiering_only,
                    page=agent_request.page,
                    limit=agent_request.limit,
                ),
            ),
        )

    @mcp.tool(
        name="find_movie_showings",
        annotations=READ_ONLY_TOOL_ANNOTATIONS,
        version=MCP_FACADE_VERSION,
    )
    async def find_movie_showings(
        ctx: Context,
        city: CityInput = None,
        location_slug: LocationSlugInput = None,
        movie_id: MovieIdInput = None,
        cinema_id: CinemaIdInput = None,
        date: ShowingCalendarDateInput = None,
        date_from: ShowingDateFromInput = None,
        date_to: ShowingDateToInput = None,
        timezone: TimezoneInput = None,
        free_only: OptionalBoolInput = None,
        page: PageInput = 1,
        limit: SearchLimitInput = 10,
    ) -> dict[str, Any]:
        """Find verified cinema showings with movie, cinema, date, time and available price information.

        Use this for actual screening times. When no date fields are supplied, the next seven days are searched. The result confirms only showings explicitly returned by KudaGo.
        """
        tool_name = "find_movie_showings"
        try:
            agent_request = FindMovieShowingsInput(
                city=city,
                location_slug=location_slug,
                movie_id=movie_id,
                cinema_id=cinema_id,
                date=date,
                date_from=date_from,
                date_to=date_to,
                timezone=timezone,
                free_only=free_only,
                page=page,
                limit=limit,
            )
            applied_timezone = (
                resolve_calendar_timezone(
                    timezone_name=agent_request.timezone,
                    location_slug=agent_request.location_slug,
                    location_text=agent_request.city,
                )
                if agent_request.has_window
                else None
            )
            actual_since, actual_until = to_utc_window(
                single_date=agent_request.date,
                date_from=agent_request.date_from,
                date_to=agent_request.date_to,
                timezone_name=applied_timezone,
            )
            request = MovieShowingsSearchRequest(
                **city_payload(
                    city=agent_request.city,
                    location_slug=agent_request.location_slug,
                ),
                movie_id=agent_request.movie_id,
                place_id=agent_request.cinema_id,
                actual_since=actual_since,
                actual_until=actual_until,
                is_free=agent_request.free_only,
                page=agent_request.page,
                page_size=agent_request.limit,
                lang="ru",
            )
        except ValidationError as exc:
            return validation_error(tool_name, exc)

        return await run_mcp_command(
            redis=ctx.lifespan_context["arq_redis"],
            tool_name=tool_name,
            endpoint="mcp://tools/find_movie_showings",
            command="movie_showings.search",
            payload=request.model_dump(),
            request_text=agent_request.city or agent_request.location_slug.value,
            data_factory=partial(
                serialize_movie_showings,
                actual_since=actual_since,
                actual_until=actual_until,
                applied_timezone=applied_timezone,
                default_window_applied=not agent_request.has_window,
                applied_filters=agent_filters(
                    city=agent_request.city,
                    location_slug=agent_request.location_slug,
                    movie_id=agent_request.movie_id,
                    cinema_id=agent_request.cinema_id,
                    date=agent_request.date,
                    date_from=agent_request.date_from,
                    date_to=agent_request.date_to,
                    timezone=applied_timezone,
                    free_only=agent_request.free_only,
                    page=agent_request.page,
                    limit=agent_request.limit,
                ),
            ),
        )


__all__ = ["register_cinema_tools"]

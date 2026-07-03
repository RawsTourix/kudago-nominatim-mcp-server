from typing import Any

from fastmcp import FastMCP
from pydantic import ValidationError

from app.mcp.envelopes import mcp_error
from app.mcp.executor import run_mcp_command
from app.schemas.events import EventsSearchRequest
from app.schemas.lists import ListsSearchRequest
from app.schemas.movie_showings import MovieShowingsSearchRequest
from app.schemas.movies import MoviesSearchRequest
from app.schemas.news import NewsSearchRequest
from app.schemas.places import PlacesSearchRequest


def register_search_tools(mcp: FastMCP) -> None:
    @mcp.tool(name="events")
    async def events(
        location: str | None = None,
        place_query: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        radius: int | None = None,
        actual_since: str | int | None = None,
        actual_until: str | int | None = None,
        categories: str | None = None,
        tags: str | None = None,
        is_free: bool | None = None,
        include_past: bool = False,
        page: int = 1,
        page_size: int = 10,
        lang: str | None = "ru",
    ) -> dict[str, Any]:
        """Search KudaGo events using deterministic filters.

        Use this for events filtered by a KudaGo location, a free-form place,
        coordinates and radius, dates, categories, tags, or free admission.
        Use location for a known KudaGo slug such as msk, or place_query for a
        city, district, address, or landmark that needs resolution.
        """
        tool_name = "events"
        try:
            request = EventsSearchRequest(
                location=location,
                place_query=place_query,
                lat=lat,
                lon=lon,
                radius=radius,
                actual_since=actual_since,
                actual_until=actual_until,
                categories=categories,
                tags=tags,
                is_free=is_free,
                include_past=include_past,
                page=page,
                page_size=page_size,
                lang=lang,
            )
        except ValidationError as exc:
            return mcp_error(
                tool=tool_name,
                message=str(exc),
                error_type=exc.__class__.__name__,
            )

        return await run_mcp_command(
            tool_name=tool_name,
            endpoint="mcp://tools/events",
            command="events.search",
            payload=request.model_dump(),
            request_text=request.place_query or request.location,
        )

    @mcp.tool(name="movies")
    async def movies(
        location: str | None = None,
        place_query: str | None = None,
        place_id: int | None = None,
        tags: str | None = None,
        is_free: bool | None = None,
        premiering_in_location: bool | None = None,
        actual_since: str | int | None = None,
        actual_until: str | int | None = None,
        include_past: bool = False,
        page: int = 1,
        page_size: int = 10,
        lang: str | None = "ru",
    ) -> dict[str, Any]:
        """Search KudaGo movies using location, cinema, and date filters.

        Use a KudaGo location slug or place_id. A free-form place_query may be
        resolved to a supported KudaGo location; coordinate-only results are
        not supported by the movies endpoint.
        """
        tool_name = "movies"
        try:
            request = MoviesSearchRequest(
                location=location,
                place_query=place_query,
                place_id=place_id,
                tags=tags,
                is_free=is_free,
                premiering_in_location=premiering_in_location,
                actual_since=actual_since,
                actual_until=actual_until,
                include_past=include_past,
                page=page,
                page_size=page_size,
                lang=lang,
            )
        except ValidationError as exc:
            return mcp_error(
                tool=tool_name,
                message=str(exc),
                error_type=exc.__class__.__name__,
            )

        return await run_mcp_command(
            tool_name=tool_name,
            endpoint="mcp://tools/movies",
            command="movies.search",
            payload=request.model_dump(),
            request_text=request.place_query or request.location,
        )

    @mcp.tool(name="movie_showings")
    async def movie_showings(
        location: str | None = None,
        place_query: str | None = None,
        movie_id: int | None = None,
        place_id: int | None = None,
        actual_since: str | int | None = None,
        actual_until: str | int | None = None,
        is_free: bool | None = None,
        page: int = 1,
        page_size: int = 10,
        lang: str | None = "ru",
    ) -> dict[str, Any]:
        """Find actual cinema showings and cinemas for a movie or location.

        Use this after movies to find where and when a film is showing. When
        movie_id is supplied, the movie-specific showings endpoint is used.
        Date bounds must be provided together; when both are omitted, the next
        seven days are searched.
        """
        tool_name = "movie_showings"
        try:
            request = MovieShowingsSearchRequest(
                location=location,
                place_query=place_query,
                movie_id=movie_id,
                place_id=place_id,
                actual_since=actual_since,
                actual_until=actual_until,
                is_free=is_free,
                page=page,
                page_size=page_size,
                lang=lang,
            )
        except ValidationError as exc:
            return mcp_error(
                tool=tool_name,
                message=str(exc),
                error_type=exc.__class__.__name__,
            )

        return await run_mcp_command(
            tool_name=tool_name,
            endpoint="mcp://tools/movie_showings",
            command="movie_showings.search",
            payload=request.model_dump(),
            request_text=request.place_query or request.location,
        )

    @mcp.tool(name="news")
    async def news(
        location: str | None = None,
        place_query: str | None = None,
        tags: str | None = None,
        actual_only: bool | None = None,
        page: int = 1,
        page_size: int = 10,
        lang: str | None = "ru",
    ) -> dict[str, Any]:
        """Search KudaGo news for a supported KudaGo location.

        Use location for a known slug such as msk, or place_query for a city
        name that can be matched to KudaGo. Coordinate-only locations are not
        supported by the upstream news endpoint.
        """
        tool_name = "news"
        try:
            request = NewsSearchRequest(
                location=location,
                place_query=place_query,
                tags=tags,
                actual_only=actual_only,
                page=page,
                page_size=page_size,
                lang=lang,
            )
        except ValidationError as exc:
            return mcp_error(
                tool=tool_name,
                message=str(exc),
                error_type=exc.__class__.__name__,
            )

        return await run_mcp_command(
            tool_name=tool_name,
            endpoint="mcp://tools/news",
            command="news.search",
            payload=request.model_dump(),
            request_text=request.place_query or request.location,
        )

    @mcp.tool(name="lists")
    async def lists(
        location: str | None = None,
        place_query: str | None = None,
        tags: str | None = None,
        page: int = 1,
        page_size: int = 10,
        lang: str | None = "ru",
    ) -> dict[str, Any]:
        """Search KudaGo editorial lists for a supported location.

        Use location for a known slug such as msk, or place_query for a city
        name that can be matched to KudaGo. Coordinate-only locations are not
        supported by the upstream lists endpoint.
        """
        tool_name = "lists"
        try:
            request = ListsSearchRequest(
                location=location,
                place_query=place_query,
                tags=tags,
                page=page,
                page_size=page_size,
                lang=lang,
            )
        except ValidationError as exc:
            return mcp_error(
                tool=tool_name,
                message=str(exc),
                error_type=exc.__class__.__name__,
            )

        return await run_mcp_command(
            tool_name=tool_name,
            endpoint="mcp://tools/lists",
            command="lists.search",
            payload=request.model_dump(),
            request_text=request.place_query or request.location,
        )

    @mcp.tool(name="places")
    async def places(
        location: str | None = None,
        place_query: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        radius: int | None = None,
        categories: str | None = None,
        tags: str | None = None,
        has_showings: bool | None = None,
        showing_since: str | int | None = None,
        showing_until: str | int | None = None,
        page: int = 1,
        page_size: int = 10,
        lang: str | None = "ru",
    ) -> dict[str, Any]:
        """Search general KudaGo places using location, geo, and filters.

        Use location for a known KudaGo slug such as msk, place_query for a
        free-form place, or provide lat, lon, and radius together. Avoid
        has_showings for cinema availability because the upstream places
        endpoint may time out. Use movie_showings to find actual cinema
        showings and cinemas instead.
        """
        tool_name = "places"
        try:
            request = PlacesSearchRequest(
                location=location,
                place_query=place_query,
                lat=lat,
                lon=lon,
                radius=radius,
                categories=categories,
                tags=tags,
                has_showings=has_showings,
                showing_since=showing_since,
                showing_until=showing_until,
                page=page,
                page_size=page_size,
                lang=lang,
            )
        except ValidationError as exc:
            return mcp_error(
                tool=tool_name,
                message=str(exc),
                error_type=exc.__class__.__name__,
            )

        return await run_mcp_command(
            tool_name=tool_name,
            endpoint="mcp://tools/places",
            command="places.search",
            payload=request.model_dump(),
            request_text=request.place_query or request.location,
        )

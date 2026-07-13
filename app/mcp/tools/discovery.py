from __future__ import annotations

from functools import partial
from typing import Any

from fastmcp import FastMCP
from pydantic import ValidationError

from app.application.contracts import CommandOutput
from app.mcp.executor import run_mcp_command
from app.mcp.mappers import enum_values_to_csv, location_payload, to_utc_window
from app.mcp.schemas.common import (
    CalendarDateInput,
    CoordinatesInput,
    DateFromInput,
    DateToInput,
    LocationSlugInput,
    PageInput,
    PlaceInput,
    RadiusKmInput,
    SearchLimitInput,
    TimezoneInput,
)
from app.mcp.schemas.discovery import (
    CountryCodesInput,
    EventCategoriesInput,
    FindEventsInput,
    FindPlacesInput,
    LanguageInput,
    OptionalBoolInput,
    PlaceCategoriesInput,
    ResolveLimitInput,
    ResolveLocationInput,
    ResolvePlaceInput,
)
from app.mcp.serializers import serialize_events, serialize_places
from app.mcp.tools._common import (
    MCP_FACADE_VERSION,
    READ_ONLY_TOOL_ANNOTATIONS,
    validation_error,
)
from app.schemas.events import EventsSearchRequest
from app.schemas.geo import GeoResolveRequest
from app.schemas.places import PlacesSearchRequest


def register_discovery_tools(mcp: FastMCP) -> None:
    @mcp.tool(
        name="resolve_location",
        annotations=READ_ONLY_TOOL_ANNOTATIONS,
        version=MCP_FACADE_VERSION,
    )
    async def resolve_location(
        place: ResolvePlaceInput,
        country_codes: CountryCodesInput = None,
        language: LanguageInput = "ru",
        limit: ResolveLimitInput = 5,
    ) -> dict[str, Any]:
        """Resolve a free-form location name with Nominatim and return coordinate candidates.

        Use this when exact coordinates are required by another tool. If multiple candidates are returned, select one from user context or ask for clarification; do not silently combine candidates.
        """
        tool_name = "resolve_location"
        try:
            agent_request = ResolveLocationInput(
                place=place,
                country_codes=country_codes,
                language=language,
                limit=limit,
            )
            request = GeoResolveRequest(
                query=agent_request.place,
                countrycodes=(
                    ",".join(agent_request.country_codes)
                    if agent_request.country_codes is not None
                    else None
                ),
                limit=agent_request.limit,
                accept_language=agent_request.language,
            )
        except ValidationError as exc:
            return validation_error(tool_name, exc)

        return await run_mcp_command(
            tool_name=tool_name,
            endpoint="mcp://tools/resolve_location",
            command="geo.resolve",
            payload=request.model_dump(),
            request_text=request.query,
            data_factory=_serialize_location,
        )

    @mcp.tool(
        name="find_events",
        annotations=READ_ONLY_TOOL_ANNOTATIONS,
        version=MCP_FACADE_VERSION,
    )
    async def find_events(
        place: PlaceInput = None,
        location_slug: LocationSlugInput = None,
        coordinates: CoordinatesInput = None,
        radius_km: RadiusKmInput = None,
        date: CalendarDateInput = None,
        date_from: DateFromInput = None,
        date_to: DateToInput = None,
        timezone: TimezoneInput = "+03:00",
        categories: EventCategoriesInput = None,
        free_only: OptionalBoolInput = None,
        page: PageInput = 1,
        limit: SearchLimitInput = 10,
    ) -> dict[str, Any]:
        """Find scheduled KudaGo events for a location and calendar date range.

        Results contain events whose occurrence dates match the requested window, not general venues. Provide exactly one location source. Only matching occurrence dates are returned to the agent.
        """
        tool_name = "find_events"
        try:
            agent_request = FindEventsInput(
                place=place,
                location_slug=location_slug,
                coordinates=coordinates,
                radius_km=radius_km,
                date=date,
                date_from=date_from,
                date_to=date_to,
                timezone=timezone,
                categories=categories,
                free_only=free_only,
                page=page,
                limit=limit,
            )
            actual_since, actual_until = to_utc_window(
                single_date=agent_request.date,
                date_from=agent_request.date_from,
                date_to=agent_request.date_to,
                timezone_name=agent_request.timezone,
            )
            assert actual_since is not None and actual_until is not None
            request = EventsSearchRequest(
                **location_payload(
                    place=agent_request.place,
                    location_slug=agent_request.location_slug,
                    coordinates=agent_request.coordinates,
                    radius_km=agent_request.radius_km,
                ),
                actual_since=actual_since,
                actual_until=actual_until,
                include_past=True,
                categories=enum_values_to_csv(agent_request.categories),
                is_free=agent_request.free_only,
                page=agent_request.page,
                page_size=agent_request.limit,
                lang="ru",
            )
        except ValidationError as exc:
            return validation_error(tool_name, exc)

        return await run_mcp_command(
            tool_name=tool_name,
            endpoint="mcp://tools/find_events",
            command="events.search",
            payload=request.model_dump(),
            request_text=agent_request.place or _enum_value(agent_request.location_slug),
            data_factory=partial(
                serialize_events,
                actual_since=actual_since,
                actual_until=actual_until,
            ),
        )

    @mcp.tool(
        name="find_places",
        annotations=READ_ONLY_TOOL_ANNOTATIONS,
        version=MCP_FACADE_VERSION,
    )
    async def find_places(
        place: PlaceInput = None,
        location_slug: LocationSlugInput = None,
        coordinates: CoordinatesInput = None,
        radius_km: RadiusKmInput = None,
        categories: PlaceCategoriesInput = None,
        page: PageInput = 1,
        limit: SearchLimitInput = 10,
    ) -> dict[str, Any]:
        """Find KudaGo venues, attractions and other places.

        A returned item confirms that the place exists, not that an event is scheduled there. Use find_events for scheduled events and find_movie_showings for actual cinema times.
        """
        tool_name = "find_places"
        try:
            agent_request = FindPlacesInput(
                place=place,
                location_slug=location_slug,
                coordinates=coordinates,
                radius_km=radius_km,
                categories=categories,
                page=page,
                limit=limit,
            )
            request = PlacesSearchRequest(
                **location_payload(
                    place=agent_request.place,
                    location_slug=agent_request.location_slug,
                    coordinates=agent_request.coordinates,
                    radius_km=agent_request.radius_km,
                ),
                categories=enum_values_to_csv(agent_request.categories),
                page=agent_request.page,
                page_size=agent_request.limit,
                lang="ru",
            )
        except ValidationError as exc:
            return validation_error(tool_name, exc)

        return await run_mcp_command(
            tool_name=tool_name,
            endpoint="mcp://tools/find_places",
            command="places.search",
            payload=request.model_dump(),
            request_text=agent_request.place or _enum_value(agent_request.location_slug),
            data_factory=serialize_places,
        )


def _serialize_location(output: CommandOutput) -> dict[str, Any]:
    payload = output.result_payload
    candidates = payload.get("candidates")
    compact_candidates = []
    if isinstance(candidates, list):
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            compact_candidates.append(
                {
                    key: candidate[key]
                    for key in ("display_name", "name", "type", "lat", "lon")
                    if key in candidate
                }
            )
    return {
        "status": output.status,
        "source": payload.get("source"),
        "query": payload.get("query"),
        "candidates": compact_candidates,
    }


def _enum_value(value: Any) -> str | None:
    return value.value if value is not None else None


__all__ = ["register_discovery_tools"]

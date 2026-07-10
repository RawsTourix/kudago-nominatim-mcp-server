from datetime import datetime
from typing import Any

from fastmcp import FastMCP
from pydantic import ValidationError

from app.mcp.envelopes import mcp_error
from app.mcp.executor import run_mcp_command
from app.schemas.routing import (
    StreetRouteProfile,
    StreetRouteRequest,
    TransitMode,
    TransitRouteRequest,
)


def register_routing_tools(mcp: FastMCP) -> None:
    @mcp.tool(name="transit_route")
    async def transit_route(
        origin_lat: float,
        origin_lon: float,
        destination_lat: float,
        destination_lon: float,
        time: datetime | None = None,
        arrive_by: bool = False,
        transit_modes: list[TransitMode] | None = None,
        max_transfers: int | None = None,
        max_travel_time_minutes: int | None = None,
        min_transfer_time_minutes: int | None = None,
        num_itineraries: int = 3,
        search_window_seconds: int = 900,
        language: str | None = "ru",
    ) -> dict[str, Any]:
        """Build a verified public transport journey between coordinate points.

        Use this tool for trains, suburban rail, metro, buses, trams, ferries,
        transfers, and the walking access/egress legs included in the returned
        journey.

        The returned route data is authoritative. Do not invent or add stations,
        route numbers, transfers, departure times, arrival times, or transport
        legs that are absent from the result.

        Use resolve_place first when only a place name or address is known.
        Do not use street_route to reconstruct walking legs already present
        inside a returned transit itinerary.
        """
        tool_name = "transit_route"
        try:
            request = TransitRouteRequest(
                origin_lat=origin_lat,
                origin_lon=origin_lon,
                destination_lat=destination_lat,
                destination_lon=destination_lon,
                time=time,
                arrive_by=arrive_by,
                transit_modes=transit_modes,
                max_transfers=max_transfers,
                max_travel_time_minutes=max_travel_time_minutes,
                min_transfer_time_minutes=min_transfer_time_minutes,
                num_itineraries=num_itineraries,
                search_window_seconds=search_window_seconds,
                language=language,
            )
        except ValidationError as exc:
            return mcp_error(
                tool=tool_name,
                message=str(exc),
                error_type=exc.__class__.__name__,
            )

        return await run_mcp_command(
            tool_name=tool_name,
            endpoint="mcp://tools/transit_route",
            command="routing.transit.plan",
            payload=request.model_dump(mode="json"),
            request_text=_request_text(request),
        )

    @mcp.tool(name="street_route")
    async def street_route(
        origin_lat: float,
        origin_lon: float,
        destination_lat: float,
        destination_lon: float,
        profile: StreetRouteProfile = StreetRouteProfile.WALKING,
        language: str | None = "ru",
        include_instructions: bool = True,
        include_geometry: bool = False,
    ) -> dict[str, Any]:
        """Build a verified walking, cycling, or driving route between points.

        Use this tool only for independent street routes. It does not provide
        public transport lines, stops, schedules, transfers, or departure times.

        Do not infer public transport information from this result.
        Use resolve_place first when only a place name or address is known.
        """
        tool_name = "street_route"
        try:
            request = StreetRouteRequest(
                origin_lat=origin_lat,
                origin_lon=origin_lon,
                destination_lat=destination_lat,
                destination_lon=destination_lon,
                profile=profile,
                language=language,
                include_instructions=include_instructions,
                include_geometry=include_geometry,
            )
        except ValidationError as exc:
            return mcp_error(
                tool=tool_name,
                message=str(exc),
                error_type=exc.__class__.__name__,
            )

        return await run_mcp_command(
            tool_name=tool_name,
            endpoint="mcp://tools/street_route",
            command="routing.street.plan",
            payload=request.model_dump(mode="json"),
            request_text=_request_text(request),
        )


def _request_text(request: TransitRouteRequest | StreetRouteRequest) -> str:
    return (
        f"{request.origin_lat},{request.origin_lon} -> "
        f"{request.destination_lat},{request.destination_lon}"
    )

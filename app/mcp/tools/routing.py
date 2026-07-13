from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastmcp import FastMCP
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.mcp.executor import run_mcp_command
from app.mcp.mappers import STREET_MODE_MAP, transit_modes, transit_time
from app.mcp.schemas.common import Coordinates
from app.mcp.schemas.routing import (
    ArrivalTimeInput,
    DepartureTimeInput,
    DestinationInput,
    MaxTransfersInput,
    OriginInput,
    PlanPublicTransportInput,
    PlanStreetRouteInput,
    PublicTransportModesInput,
    RouteLimitInput,
    StreetModeInput,
    StreetTravelMode,
)
from app.mcp.serializers import serialize_routing
from app.mcp.tools._common import (
    MCP_FACADE_VERSION,
    READ_ONLY_TOOL_ANNOTATIONS,
    validation_error,
)
from app.schemas.routing import StreetRouteRequest, TransitRouteRequest


logger = logging.getLogger(__name__)


def register_routing_tools(
    mcp: FastMCP,
    *,
    settings_obj: Settings = settings,
) -> None:
    if (settings_obj.transitous_user_agent or "").strip():
        _register_public_transport_tool(mcp)
    else:
        logger.warning(
            "plan_public_transport is not registered: TRANSITOUS_USER_AGENT is empty"
        )

    if (settings_obj.openrouteservice_api_key or "").strip():
        _register_street_route_tool(mcp)
    else:
        logger.warning(
            "plan_street_route is not registered: OPENROUTESERVICE_API_KEY is empty"
        )


def _register_public_transport_tool(mcp: FastMCP) -> None:
    @mcp.tool(
        name="plan_public_transport",
        annotations=READ_ONLY_TOOL_ANNOTATIONS,
        version=MCP_FACADE_VERSION,
    )
    async def plan_public_transport(
        origin: OriginInput,
        destination: DestinationInput,
        departure_time: DepartureTimeInput = None,
        arrival_time: ArrivalTimeInput = None,
        modes: PublicTransportModesInput = None,
        max_transfers: MaxTransfersInput = None,
        limit: RouteLimitInput = 3,
    ) -> dict[str, Any]:
        """Plan a verified public-transport journey between two coordinate points.

        Use resolve_location first when coordinates are unknown. Walking access, transfers and egress are included. Trust route facts only when result_status is ok and route_verified is true.
        """
        tool_name = "plan_public_transport"
        try:
            agent_request = PlanPublicTransportInput(
                origin=origin,
                destination=destination,
                departure_time=departure_time,
                arrival_time=arrival_time,
                modes=modes,
                max_transfers=max_transfers,
                limit=limit,
            )
            effective_time, arrive_by = transit_time(
                agent_request.departure_time,
                agent_request.arrival_time,
            )
            request = TransitRouteRequest(
                origin_lat=agent_request.origin.latitude,
                origin_lon=agent_request.origin.longitude,
                destination_lat=agent_request.destination.latitude,
                destination_lon=agent_request.destination.longitude,
                time=effective_time,
                arrive_by=arrive_by,
                transit_modes=transit_modes(agent_request.modes),
                max_transfers=agent_request.max_transfers,
                num_itineraries=agent_request.limit,
                language="ru",
            )
        except ValidationError as exc:
            return validation_error(tool_name, exc)

        return await run_mcp_command(
            tool_name=tool_name,
            endpoint="mcp://tools/plan_public_transport",
            command="routing.transit.plan",
            payload=request.model_dump(mode="json"),
            request_text=_request_text(agent_request.origin, agent_request.destination),
            data_factory=serialize_routing,
        )


def _register_street_route_tool(mcp: FastMCP) -> None:
    @mcp.tool(
        name="plan_street_route",
        annotations=READ_ONLY_TOOL_ANNOTATIONS,
        version=MCP_FACADE_VERSION,
    )
    async def plan_street_route(
        origin: OriginInput,
        destination: DestinationInput,
        mode: StreetModeInput = StreetTravelMode.WALKING,
    ) -> dict[str, Any]:
        """Plan a verified independent walking, cycling or driving route between two coordinate points.

        This tool does not provide public-transport lines, stops, schedules or transfers. Use plan_public_transport for those facts; full route geometry is omitted from MCP.
        """
        tool_name = "plan_street_route"
        try:
            agent_request = PlanStreetRouteInput(
                origin=origin,
                destination=destination,
                mode=mode,
            )
            request = StreetRouteRequest(
                origin_lat=agent_request.origin.latitude,
                origin_lon=agent_request.origin.longitude,
                destination_lat=agent_request.destination.latitude,
                destination_lon=agent_request.destination.longitude,
                profile=STREET_MODE_MAP[agent_request.mode],
                language="ru",
                include_instructions=True,
                include_geometry=False,
            )
        except ValidationError as exc:
            return validation_error(tool_name, exc)

        return await run_mcp_command(
            tool_name=tool_name,
            endpoint="mcp://tools/plan_street_route",
            command="routing.street.plan",
            payload=request.model_dump(mode="json"),
            request_text=_request_text(agent_request.origin, agent_request.destination),
            data_factory=serialize_routing,
        )


def _request_text(origin: Coordinates, destination: Coordinates) -> str:
    return (
        f"{origin.latitude},{origin.longitude} -> "
        f"{destination.latitude},{destination.longitude}"
    )


__all__ = ["register_routing_tools"]

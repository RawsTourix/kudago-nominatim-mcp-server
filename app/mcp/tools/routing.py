from __future__ import annotations

import logging
from functools import partial
from typing import Any

from fastmcp import Context, FastMCP
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.mcp.executor import run_mcp_command
from app.mcp.mappers import STREET_MODE_MAP, transit_modes, transit_time
from app.mcp.schemas.routing import (
    ArrivalTimeInput,
    DepartureTimeInput,
    DestinationInput,
    MaxRoutesInput,
    MaxTransfersInput,
    OriginInput,
    PlanPublicTransportInput,
    PlanStreetRouteInput,
    PublicTransportModesInput,
    RoutePoint,
    StreetModeInput,
    StreetTravelMode,
)
from app.mcp.serializers import (
    serialize_public_transport,
    serialize_street_route,
)
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
        ctx: Context,
        origin: OriginInput,
        destination: DestinationInput,
        departure_time: DepartureTimeInput = None,
        arrival_time: ArrivalTimeInput = None,
        transport_modes: PublicTransportModesInput = None,
        max_transfers: MaxTransfersInput = None,
        max_routes: MaxRoutesInput = 3,
    ) -> dict[str, Any]:
        """Plan a verified public-transport journey between two coordinate points.

        Provide exactly one timezone-aware departure_time or arrival_time. Omit transport_modes unless the user explicitly restricts transport types. A no_route result applies only to these exact points, time and restrictions. Use resolve_location first when coordinates are unknown. Walking access, transfers and egress are included. Trust route facts only when result_status is ok and route_verified is true.
        """
        tool_name = "plan_public_transport"
        try:
            agent_request = PlanPublicTransportInput(
                origin=origin,
                destination=destination,
                departure_time=departure_time,
                arrival_time=arrival_time,
                transport_modes=transport_modes,
                max_transfers=max_transfers,
                max_routes=max_routes,
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
                transit_modes=transit_modes(agent_request.transport_modes),
                max_transfers=agent_request.max_transfers,
                num_itineraries=agent_request.max_routes,
                language="ru",
            )
        except ValidationError as exc:
            return validation_error(tool_name, exc)

        return await run_mcp_command(
            redis=ctx.lifespan_context["arq_redis"],
            wait_timeout_seconds=ctx.lifespan_context[
                "mcp_job_wait_timeout_seconds"
            ],
            tool_name=tool_name,
            endpoint="mcp://tools/plan_public_transport",
            command="routing.transit.plan",
            payload=request.model_dump(mode="json"),
            request_text=_request_text(agent_request.origin, agent_request.destination),
            data_factory=partial(
                serialize_public_transport,
                agent_request=agent_request,
            ),
        )


def _register_street_route_tool(mcp: FastMCP) -> None:
    @mcp.tool(
        name="plan_street_route",
        annotations=READ_ONLY_TOOL_ANNOTATIONS,
        version=MCP_FACADE_VERSION,
    )
    async def plan_street_route(
        ctx: Context,
        origin: OriginInput,
        destination: DestinationInput,
        travel_mode: StreetModeInput = StreetTravelMode.WALKING,
    ) -> dict[str, Any]:
        """Plan a verified independent walking, cycling or driving route between two coordinate points.

        This tool does not provide public-transport lines, stops, schedules or transfers. Use plan_public_transport for those facts; full route geometry is omitted from MCP.
        """
        tool_name = "plan_street_route"
        try:
            agent_request = PlanStreetRouteInput(
                origin=origin,
                destination=destination,
                travel_mode=travel_mode,
            )
            request = StreetRouteRequest(
                origin_lat=agent_request.origin.latitude,
                origin_lon=agent_request.origin.longitude,
                destination_lat=agent_request.destination.latitude,
                destination_lon=agent_request.destination.longitude,
                profile=STREET_MODE_MAP[agent_request.travel_mode],
                language="ru",
                include_instructions=True,
                include_geometry=False,
            )
        except ValidationError as exc:
            return validation_error(tool_name, exc)

        return await run_mcp_command(
            redis=ctx.lifespan_context["arq_redis"],
            wait_timeout_seconds=ctx.lifespan_context[
                "mcp_job_wait_timeout_seconds"
            ],
            tool_name=tool_name,
            endpoint="mcp://tools/plan_street_route",
            command="routing.street.plan",
            payload=request.model_dump(mode="json"),
            request_text=_request_text(agent_request.origin, agent_request.destination),
            data_factory=partial(
                serialize_street_route,
                agent_request=agent_request,
            ),
        )


def _request_text(origin: RoutePoint, destination: RoutePoint) -> str:
    return f"{_point_text(origin)} -> {_point_text(destination)}"


def _point_text(point: RoutePoint) -> str:
    coordinates = f"{point.latitude},{point.longitude}"
    return f"{point.label} ({coordinates})" if point.label else coordinates


__all__ = ["register_routing_tools"]

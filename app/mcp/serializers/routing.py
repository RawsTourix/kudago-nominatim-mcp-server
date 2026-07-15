from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.application.contracts import CommandOutput
from app.integrations.transitous.routing_policy import (
    TRANSIT_AGENT_WALKING_MODE,
    TRANSIT_DIRECT_MODES,
    TRANSIT_MAX_ACCESS_SECONDS,
    TRANSIT_MAX_EGRESS_SECONDS,
)
from app.mcp.schemas.routing import (
    PlanPublicTransportInput,
    PlanStreetRouteInput,
    RoutePoint,
)
from app.mcp.serializers.common import (
    ROUTING_RESPONSE_LIMIT_BYTES,
    enforce_item_limit,
)


REMOVED_ROUTE_FIELDS = {
    "geometry",
    "raw_response",
    "requestParameters",
    "debugOutput",
    "pageCursor",
    "nextPageCursor",
    "previousPageCursor",
}
PUBLIC_TRANSPORT_RETRY_HINTS = [
    {
        "code": "verify_route_points",
        "message": (
            "Check that both coordinates match the intended origin and "
            "destination."
        ),
    },
    {
        "code": "try_nearby_time",
        "message": (
            "Try a nearby departure or arrival time because the provider "
            "returned no itinerary for the exact requested time."
        ),
    },
    {
        "code": "check_provider_coverage",
        "message": (
            "Check provider coverage separately; this response does not "
            "include a structured coverage status."
        ),
    },
    {
        "code": "check_walking_access_limit",
        "message": (
            "Walking access and egress are limited to "
            f"{TRANSIT_MAX_ACCESS_SECONDS} seconds each. Try "
            "coordinates of a nearer station, stop or entrance and combine "
            "the result with plan_street_route."
        ),
    },
]
REMOVE_MODE_RESTRICTIONS_HINT = {
    "code": "remove_mode_restrictions",
    "message": (
        "Omit transport_modes to allow every transit mode supported by the "
        "provider."
    ),
}
STREET_RETRY_HINTS = [
    {
        "code": "verify_route_points",
        "message": (
            "Check that both coordinates are located on or near a routeable "
            "street or path."
        ),
    },
    {
        "code": "try_nearby_point",
        "message": (
            "Try a nearby entrance or road-access point if the destination is "
            "inside a large property."
        ),
    },
]


def serialize_public_transport(
    output: CommandOutput,
    *,
    agent_request: PlanPublicTransportInput,
) -> dict[str, Any]:
    payload = output.result_payload
    result_status = _result_status(payload, output)
    routes = _compact_routes(payload.get("routes"))
    if result_status != "ok":
        routes = []

    result: dict[str, Any] = {
        "result_kind": "public_transport_routes",
        "result_status": result_status,
        "route_verified": result_status == "ok" and bool(routes),
        "provider": payload.get("provider", "transitous"),
        "request": _public_transport_request(agent_request),
        "returned": payload.get("returned", len(routes)),
        "routes": routes,
    }
    if result_status == "no_route":
        retry_hints = deepcopy(PUBLIC_TRANSPORT_RETRY_HINTS)
        if agent_request.transport_modes is not None:
            retry_hints.append(deepcopy(REMOVE_MODE_RESTRICTIONS_HINT))
        result["diagnostic"] = {
            "code": "provider_returned_no_itineraries",
            "coverage_status": "unknown",
            "message": (
                "The provider returned no itinerary for the exact requested "
                "points, time and restrictions."
            ),
        }
        result["retry_hints"] = retry_hints
    result["warnings"] = _list_value(payload.get("warnings"))
    result["attribution"] = _list_value(payload.get("attribution"))
    return _limit_routes(result)


def serialize_street_route(
    output: CommandOutput,
    *,
    agent_request: PlanStreetRouteInput,
) -> dict[str, Any]:
    payload = output.result_payload
    result_status = _result_status(payload, output)
    routes = _compact_routes(payload.get("routes"))
    if result_status != "ok":
        routes = []

    result: dict[str, Any] = {
        "result_kind": "street_route",
        "result_status": result_status,
        "route_verified": result_status == "ok" and bool(routes),
        "provider": payload.get("provider", "openrouteservice"),
        "request": {
            "origin": _route_point(agent_request.origin),
            "destination": _route_point(agent_request.destination),
            "travel_mode": agent_request.travel_mode.value,
        },
        "returned": payload.get("returned", len(routes)),
        "routes": routes,
        "warnings": _list_value(payload.get("warnings")),
        "attribution": _list_value(payload.get("attribution")),
    }
    if result_status == "no_route":
        result["diagnostic"] = {
            "code": "provider_returned_no_route",
            "message": (
                "OpenRouteService could not build a route between these exact "
                "coordinates for the selected travel mode."
            ),
        }
        result["retry_hints"] = deepcopy(STREET_RETRY_HINTS)
    return _limit_routes(result)


def _public_transport_request(
    request: PlanPublicTransportInput,
) -> dict[str, Any]:
    if request.departure_time is not None:
        time_constraint = {
            "type": "departure_time",
            "value": request.departure_time.isoformat(),
        }
    else:
        time_constraint = {
            "type": "arrival_time",
            "value": request.arrival_time.isoformat(),
        }

    if request.transport_modes is None:
        mode_policy = "all_provider_supported"
        modes = None
    else:
        mode_policy = "restricted"
        modes = [mode.value for mode in request.transport_modes]

    return {
        "origin": _route_point(request.origin),
        "destination": _route_point(request.destination),
        "time_constraint": time_constraint,
        "transport_mode_policy": mode_policy,
        "transport_modes": modes,
        "max_transfers": request.max_transfers,
        "max_routes": request.max_routes,
        "access_mode": TRANSIT_AGENT_WALKING_MODE,
        "egress_mode": TRANSIT_AGENT_WALKING_MODE,
        "max_access_seconds": TRANSIT_MAX_ACCESS_SECONDS,
        "max_egress_seconds": TRANSIT_MAX_EGRESS_SECONDS,
        "direct_routes_enabled": bool(TRANSIT_DIRECT_MODES),
    }


def _route_point(point: RoutePoint) -> dict[str, Any]:
    return point.model_dump(mode="json", exclude_none=True)


def _result_status(
    payload: dict[str, Any],
    output: CommandOutput,
) -> str:
    value = payload.get("status", output.status)
    return value if isinstance(value, str) else output.status


def _compact_routes(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [_compact_route(route) for route in value if isinstance(route, dict)]


def _limit_routes(result: dict[str, Any]) -> dict[str, Any]:
    limited = enforce_item_limit(
        result,
        maximum_bytes=ROUTING_RESPONSE_LIMIT_BYTES,
        item_key="routes",
    )
    limited["route_verified"] = (
        limited["result_status"] == "ok" and bool(limited["routes"])
    )
    return limited


def _compact_route(value: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    geometry_removed = False
    for key, item in value.items():
        if key in REMOVED_ROUTE_FIELDS:
            geometry_removed = geometry_removed or key == "geometry"
            continue
        result[key] = _compact_nested(item)
    if geometry_removed:
        result["geometry_hidden"] = True
    return result


def _compact_nested(value: Any) -> Any:
    if isinstance(value, list):
        return [_compact_nested(item) for item in value]
    if not isinstance(value, dict):
        return deepcopy(value)
    return {
        key: _compact_nested(item)
        for key, item in value.items()
        if key not in REMOVED_ROUTE_FIELDS
    }


def _list_value(value: Any) -> list[Any]:
    return deepcopy(value) if isinstance(value, list) else []


__all__ = ["serialize_public_transport", "serialize_street_route"]

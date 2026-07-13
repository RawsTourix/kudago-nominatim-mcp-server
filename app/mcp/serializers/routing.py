from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.application.contracts import CommandOutput
from app.mcp.serializers.common import (
    ROUTING_RESPONSE_LIMIT_BYTES,
    compact_coordinates,
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
PUBLIC_TRANSIT_MODE_NAMES = {
    "TRAM": "tram",
    "SUBWAY": "subway",
    "FERRY": "ferry",
    "BUS": "bus",
    "COACH": "coach",
    "RAIL": "rail",
    "HIGHSPEED_RAIL": "high_speed_rail",
    "LONG_DISTANCE": "long_distance_rail",
    "NIGHT_RAIL": "night_rail",
    "REGIONAL_RAIL": "regional_rail",
    "SUBURBAN": "suburban_rail",
    "FUNICULAR": "funicular",
    "AERIAL_LIFT": "aerial_lift",
}


def serialize_routing(output: CommandOutput) -> dict[str, Any]:
    payload = output.result_payload
    routes = payload.get("routes")
    compact_routes = (
        [_compact_route(route) for route in routes if isinstance(route, dict)]
        if isinstance(routes, list)
        else []
    )
    result = {
        key: deepcopy(payload[key])
        for key in (
            "status",
            "provider",
            "query",
            "returned",
            "message",
            "warnings",
            "attribution",
        )
        if key in payload
    }
    if payload.get("profile") is not None:
        result["mode"] = payload["profile"]
    result["routes"] = compact_routes
    _normalize_query(result.get("query"))
    result["route_verified"] = output.status == "ok" and bool(compact_routes)
    if not result["route_verified"]:
        result["routes"] = []
    limited = enforce_item_limit(
        result,
        maximum_bytes=ROUTING_RESPONSE_LIMIT_BYTES,
        item_key="routes",
    )
    limited["route_verified"] = output.status == "ok" and bool(limited["routes"])
    return limited


def _normalize_query(value: Any) -> None:
    if not isinstance(value, dict):
        return
    for point_name in ("origin", "destination"):
        point = compact_coordinates(value.get(point_name))
        if point is not None:
            value[point_name] = point

    modes = value.pop("transit_modes", None)
    if isinstance(modes, list):
        value["modes"] = [
            PUBLIC_TRANSIT_MODE_NAMES.get(mode, mode)
            for mode in modes
            if isinstance(mode, str)
        ]

    if "arrive_by" in value:
        arrive_by = value.pop("arrive_by") is True
        route_time = value.pop("time", None)
        if route_time is not None:
            value["arrival_time" if arrive_by else "departure_time"] = route_time


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


__all__ = ["serialize_routing"]

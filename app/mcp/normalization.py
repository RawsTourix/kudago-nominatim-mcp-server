from copy import deepcopy
from typing import Any


def compact_geo(geo: Any) -> dict[str, Any] | None:
    if not isinstance(geo, dict):
        return None

    compact = {
        key: geo[key]
        for key in (
            "status",
            "kind",
            "source",
            "query",
            "location",
            "lat",
            "lon",
            "selected_lat",
            "selected_lon",
            "radius",
        )
        if key in geo
    }

    candidates = geo.get("candidates")
    if isinstance(candidates, list):
        compact["candidates"] = [
            _compact_candidate(candidate)
            for candidate in candidates
            if isinstance(candidate, dict)
        ]

    matched_location = geo.get("matched_location")
    if isinstance(matched_location, dict):
        compact["matched_location"] = {
            key: matched_location[key]
            for key in ("slug", "name")
            if key in matched_location
        }

    return compact


def compact_mcp_data(result_payload: dict[str, Any]) -> dict[str, Any]:
    data = deepcopy(result_payload)

    if "geo" in data:
        data["geo"] = compact_geo(data["geo"])

    candidates = data.get("candidates")
    if isinstance(candidates, list):
        data["candidates"] = [
            _compact_candidate(candidate)
            for candidate in candidates
            if isinstance(candidate, dict)
        ]

    routes = data.get("routes")
    if isinstance(routes, list):
        data["routes"] = [
            _compact_route(route) if isinstance(route, dict) else route
            for route in routes
        ]

    for provider_field in (
        "raw_response",
        "requestParameters",
        "debugOutput",
        "pageCursor",
        "nextPageCursor",
        "previousPageCursor",
    ):
        data.pop(provider_field, None)

    return data


def compact_mcp_meta(meta: dict[str, Any]) -> dict[str, Any]:
    compact = dict(meta)
    compact.pop("geo", None)
    return compact


def _compact_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    namedetails = candidate.get("namedetails")
    name = candidate.get("name")
    if name is None and isinstance(namedetails, dict):
        name = namedetails.get("name")

    compact = {
        key: candidate[key]
        for key in ("display_name", "type", "lat", "lon")
        if key in candidate
    }
    if name is not None:
        compact = {"name": name, **compact}
    return compact


def _compact_route(route: dict[str, Any]) -> dict[str, Any]:
    compact = deepcopy(route)
    geometry = compact.get("geometry")
    if geometry is not None:
        compact.pop("geometry", None)
        compact["geometry_hidden"] = True
    for provider_field in ("raw_response", "debugOutput"):
        compact.pop(provider_field, None)
    return compact

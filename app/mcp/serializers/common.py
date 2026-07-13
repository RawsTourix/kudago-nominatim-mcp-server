from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from app.application.contracts import CommandOutput
from app.mcp.normalization import compact_geo


SEARCH_RESPONSE_LIMIT_BYTES = 64 * 1024
ROUTING_RESPONSE_LIMIT_BYTES = 128 * 1024


def search_base(output: CommandOutput) -> dict[str, Any]:
    payload = output.result_payload
    data: dict[str, Any] = {
        "status": output.status,
        "count": payload.get("count"),
        "returned": payload.get("returned", len(output.items)),
        "items": [],
    }
    for key in ("source", "message", "warnings", "attribution"):
        if key in payload:
            data[key] = deepcopy(payload[key])
    if isinstance(payload.get("filters"), dict):
        data["applied_filters"] = deepcopy(payload["filters"])
    geo = compact_geo(payload.get("geo"))
    if geo is not None:
        data["geo"] = geo
    return data


def enforce_item_limit(
    data: dict[str, Any],
    *,
    maximum_bytes: int = SEARCH_RESPONSE_LIMIT_BYTES,
    item_key: str = "items",
) -> dict[str, Any]:
    items = data.get(item_key)
    if not isinstance(items, list):
        return data

    original_length = len(items)
    while items and json_size(data) > maximum_bytes:
        items.pop()

    if len(items) != original_length:
        data["truncated"] = True
        data["returned_to_agent"] = len(items)
        data["full_result_available"] = True
    return data


def json_size(value: Any) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    )


def compact_coordinates(value: Any) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    lat = value.get("lat", value.get("latitude"))
    lon = value.get("lon", value.get("longitude"))
    lat_number = _coordinate_number(lat)
    lon_number = _coordinate_number(lon)
    if lat_number is None or lon_number is None:
        return None
    return {"latitude": lat_number, "longitude": lon_number}


def _coordinate_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def category_slugs(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            slug = item.get("slug")
            if isinstance(slug, str):
                result.append(slug)
    return result


def details_ref(item_type: str, item_id: Any) -> dict[str, str] | None:
    if item_id is None:
        return None
    return {"item_type": item_type, "item_id": str(item_id)}


def iso_timestamp(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
    if isinstance(value, str):
        try:
            numeric = float(value)
        except ValueError:
            return value
        return datetime.fromtimestamp(numeric, timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
    return None


def compact_place(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    result = pick(
        value,
        "id",
        "title",
        "address",
        "subway",
        "site_url",
    )
    coordinates = compact_coordinates(value.get("coords", value.get("coordinates")))
    if coordinates is not None:
        result["coordinates"] = coordinates
    return result or None


def pick(source: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {
        key: deepcopy(source[key])
        for key in keys
        if key in source and source[key] is not None
    }


__all__ = [
    "ROUTING_RESPONSE_LIMIT_BYTES",
    "SEARCH_RESPONSE_LIMIT_BYTES",
    "category_slugs",
    "compact_coordinates",
    "compact_place",
    "details_ref",
    "enforce_item_limit",
    "iso_timestamp",
    "json_size",
    "pick",
    "search_base",
]

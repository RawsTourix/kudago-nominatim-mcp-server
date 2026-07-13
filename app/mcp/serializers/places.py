from __future__ import annotations

from typing import Any

from app.application.contracts import CommandOutput
from app.mcp.serializers.common import (
    category_slugs,
    compact_coordinates,
    details_ref,
    enforce_item_limit,
    pick,
    search_base,
)


USAGE_NOTE = "These are places, not confirmed events for a selected date."


def serialize_places(
    output: CommandOutput,
    *,
    applied_filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = search_base(output, applied_filters=applied_filters)
    data.update(
        {
            "result_kind": "places",
            "schedule_verified": False,
            "usage_note": USAGE_NOTE,
        }
    )
    data["items"] = [
        _serialize_place(item)
        for item in output.items
        if isinstance(item, dict)
    ]
    data["returned"] = len(data["items"])
    return enforce_item_limit(data)


def _serialize_place(item: dict[str, Any]) -> dict[str, Any]:
    result = pick(
        item,
        "id",
        "title",
        "short_title",
        "description",
        "site_url",
        "address",
        "subway",
        "timetable",
        "phone",
        "is_closed",
    )
    coordinates = compact_coordinates(item.get("coords", item.get("coordinates")))
    if coordinates is not None:
        result["coordinates"] = coordinates
    result["categories"] = category_slugs(item.get("categories"))
    reference = details_ref("place", item.get("id"))
    if reference is not None:
        result["details_ref"] = reference
    return result


__all__ = ["USAGE_NOTE", "serialize_places"]

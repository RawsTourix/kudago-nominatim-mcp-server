from __future__ import annotations

from typing import Any

from app.application.contracts import CommandOutput
from app.mcp.serializers.common import (
    details_ref,
    enforce_item_limit,
    pick,
    search_base,
)


def serialize_guides(
    output: CommandOutput,
    *,
    applied_filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = search_base(output, applied_filters=applied_filters)
    data.update(
        {
            "result_kind": "city_guides",
            "schedule_verified": False,
            "usage_note": (
                "Editorial guides may mix object types and are not live schedules."
            ),
        }
    )
    data["items"] = [
        _serialize_guide(item)
        for item in output.items
        if isinstance(item, dict)
    ]
    data["returned"] = len(data["items"])
    return enforce_item_limit(data)


def _serialize_guide(item: dict[str, Any]) -> dict[str, Any]:
    result = pick(
        item,
        "id",
        "title",
        "publication_date",
        "description",
        "site_url",
        "favorites_count",
        "comments_count",
    )
    reference = details_ref("guide", item.get("id"))
    if reference is not None:
        result["details_ref"] = reference
    return result


__all__ = ["serialize_guides"]

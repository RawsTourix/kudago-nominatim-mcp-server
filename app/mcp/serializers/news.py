from __future__ import annotations

from typing import Any

from app.application.contracts import CommandOutput
from app.mcp.serializers.common import (
    compact_place,
    details_ref,
    enforce_item_limit,
    pick,
    search_base,
)


def serialize_news(output: CommandOutput) -> dict[str, Any]:
    data = search_base(output)
    data["result_kind"] = "city_news"
    data["items"] = [
        _serialize_news_item(item)
        for item in output.items
        if isinstance(item, dict)
    ]
    data["returned"] = len(data["items"])
    return enforce_item_limit(data)


def _serialize_news_item(item: dict[str, Any]) -> dict[str, Any]:
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
    place = compact_place(item.get("place"))
    if place is not None:
        result["place"] = place
    reference = details_ref("news", item.get("id"))
    if reference is not None:
        result["details_ref"] = reference
    return result


__all__ = ["serialize_news"]

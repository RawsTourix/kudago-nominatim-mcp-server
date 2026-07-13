from __future__ import annotations

from typing import Any

from app.application.contracts import CommandOutput
from app.mcp.serializers.common import (
    compact_place,
    enforce_item_limit,
    pick,
    search_base,
)


def serialize_movie_showings(output: CommandOutput) -> dict[str, Any]:
    data = search_base(output)
    data.update(
        {
            "result_kind": "movie_showings",
            "schedule_verified": output.status == "ok",
        }
    )
    data["items"] = [
        _serialize_showing(item)
        for item in output.items
        if isinstance(item, dict)
    ]
    data["returned"] = len(data["items"])
    return enforce_item_limit(data)


def _serialize_showing(item: dict[str, Any]) -> dict[str, Any]:
    result = pick(
        item,
        "id",
        "datetime",
        "price",
        "three_d",
        "imax",
        "four_dx",
        "original_language",
    )
    movie = item.get("movie")
    if isinstance(movie, dict):
        result["movie"] = pick(movie, "id", "title", "site_url")
    cinema = compact_place(item.get("place", item.get("cinema")))
    if cinema is not None:
        result["cinema"] = cinema
    return result


__all__ = ["serialize_movie_showings"]

from __future__ import annotations

from typing import Any

from app.application.contracts import CommandOutput
from app.mcp.serializers.common import (
    compact_place,
    enforce_item_limit,
    iso_timestamp,
    pick,
    search_base,
)


def serialize_movie_showings(
    output: CommandOutput,
    *,
    actual_since: int | None = None,
    actual_until: int | None = None,
    applied_timezone: str | None = None,
    default_window_applied: bool = False,
    applied_filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = search_base(output, applied_filters=applied_filters)
    data.update(
        {
            "result_kind": "movie_showings",
            "schedule_verified": output.status == "ok",
        }
    )
    if actual_since is not None and actual_until is not None:
        data["applied_time_window"] = {
            "start": iso_timestamp(actual_since),
            "end": iso_timestamp(actual_until),
        }
        data["applied_timezone"] = applied_timezone
    elif default_window_applied:
        filters = output.result_payload.get("filters")
        if isinstance(filters, dict):
            data["applied_time_window"] = {
                "start": iso_timestamp(filters.get("actual_since")),
                "end": iso_timestamp(filters.get("actual_until")),
                "source": "default_next_7_days",
            }
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

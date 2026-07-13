from __future__ import annotations

from typing import Any

from app.application.contracts import CommandOutput
from app.mcp.serializers.common import (
    details_ref,
    enforce_item_limit,
    iso_timestamp,
    pick,
    search_base,
)


def serialize_movies(
    output: CommandOutput,
    *,
    actual_since: int | None = None,
    actual_until: int | None = None,
    applied_timezone: str | None = None,
    applied_filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = search_base(output, applied_filters=applied_filters)
    data.update(
        {
            "result_kind": "movies",
            "showing_times_verified": False,
            "usage_note": (
                "These are movie records, not verified cinema showing times."
            ),
        }
    )
    if actual_since is not None and actual_until is not None:
        data["applied_time_window"] = {
            "start": iso_timestamp(actual_since),
            "end": iso_timestamp(actual_until),
        }
        data["applied_timezone"] = applied_timezone
    data["items"] = [
        _serialize_movie(item)
        for item in output.items
        if isinstance(item, dict)
    ]
    data["returned"] = len(data["items"])
    return enforce_item_limit(data)


def _serialize_movie(item: dict[str, Any]) -> dict[str, Any]:
    result = pick(
        item,
        "id",
        "title",
        "original_title",
        "description",
        "site_url",
        "genres",
        "country",
        "year",
        "running_time",
        "age_restriction",
    )
    reference = details_ref("movie", item.get("id"))
    if reference is not None:
        result["details_ref"] = reference
    return result


__all__ = ["serialize_movies"]

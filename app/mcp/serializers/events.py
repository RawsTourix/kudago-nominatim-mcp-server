from __future__ import annotations

from typing import Any

from app.application.contracts import CommandOutput
from app.mcp.serializers.common import (
    category_slugs,
    compact_place,
    details_ref,
    enforce_item_limit,
    iso_timestamp,
    pick,
    search_base,
)


def serialize_events(
    output: CommandOutput,
    *,
    actual_since: int,
    actual_until: int,
    applied_timezone: str,
    applied_filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = search_base(output, applied_filters=applied_filters)
    data.update(
        {
            "result_kind": "scheduled_events",
            "schedule_verified": output.status == "ok",
            "applied_timezone": applied_timezone,
            "applied_time_window": {
                "start": iso_timestamp(actual_since),
                "end": iso_timestamp(actual_until),
            },
        }
    )
    items: list[dict[str, Any]] = []
    for item in output.items:
        if not isinstance(item, dict):
            continue
        serialized = _serialize_event(item, actual_since, actual_until)
        if serialized["matching_dates"]:
            items.append(serialized)
    data["items"] = items
    data["returned"] = len(data["items"])
    return enforce_item_limit(data)


def _serialize_event(
    item: dict[str, Any],
    actual_since: int,
    actual_until: int,
) -> dict[str, Any]:
    result = pick(
        item,
        "id",
        "title",
        "short_title",
        "description",
        "site_url",
        "age_restriction",
        "price",
        "is_free",
    )
    result["categories"] = category_slugs(item.get("categories"))
    place = compact_place(item.get("place"))
    if place is not None:
        result["place"] = place
    dates = item.get("dates")
    matching_dates: list[dict[str, str | None]] = []
    if isinstance(dates, list):
        for date_item in dates:
            if not isinstance(date_item, dict):
                continue
            compact = _matching_date(date_item, actual_since, actual_until)
            if compact is not None:
                matching_dates.append(compact)
    result["matching_dates"] = matching_dates
    reference = details_ref("event", item.get("id"))
    if reference is not None:
        result["details_ref"] = reference
    return result


def _matching_date(
    item: dict[str, Any],
    actual_since: int,
    actual_until: int,
) -> dict[str, str | None] | None:
    start = _numeric_timestamp(item.get("start"))
    end = _numeric_timestamp(item.get("end"))
    if start is None:
        return None
    effective_end = end if end is not None else start
    if effective_end < actual_since or start > actual_until:
        return None
    return {
        "start": iso_timestamp(item.get("start")),
        "end": iso_timestamp(item.get("end")),
    }


def _numeric_timestamp(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


__all__ = ["serialize_events"]

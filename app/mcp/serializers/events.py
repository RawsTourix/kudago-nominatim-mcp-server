from __future__ import annotations

from math import isfinite
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
    matching_dates: list[dict[str, Any]] = []
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
) -> dict[str, Any] | None:
    is_startless = item.get("is_startless") is True
    is_endless = item.get("is_endless") is True
    start = _numeric_timestamp(item.get("start"))
    end = _numeric_timestamp(item.get("end"))

    if is_startless and is_endless:
        matches = True
    elif is_startless:
        matches = end is not None and end >= actual_since
    elif is_endless:
        matches = start is not None and start <= actual_until
    elif start is None:
        matches = False
    else:
        effective_end = end if end is not None else start
        matches = effective_end >= actual_since and start <= actual_until

    if not matches:
        return None

    return {
        "start": None if is_startless else iso_timestamp(item.get("start")),
        "end": None if is_endless else iso_timestamp(item.get("end")),
        "is_startless": is_startless,
        "is_endless": is_endless,
        "is_continuous": item.get("is_continuous") is True,
        "use_place_schedule": item.get("use_place_schedule") is True,
        "schedules": _compact_schedules(item.get("schedules")),
    }


def _compact_schedules(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        compact: dict[str, Any] = {}
        for key in ("days_of_week", "start_time", "end_time"):
            if key not in item:
                continue
            simple_value = _simple_json_value(item[key])
            if simple_value is not _INVALID_JSON_VALUE:
                compact[key] = simple_value
        if compact:
            result.append(compact)
    return result


_INVALID_JSON_VALUE = object()


def _simple_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if isfinite(value) else _INVALID_JSON_VALUE
    if isinstance(value, list):
        compact: list[Any] = []
        for item in value:
            simple_item = _simple_json_value(item)
            if simple_item is _INVALID_JSON_VALUE:
                return _INVALID_JSON_VALUE
            compact.append(simple_item)
        return compact
    return _INVALID_JSON_VALUE


def _numeric_timestamp(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return None


__all__ = ["serialize_events"]

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo


def to_utc_window(
    *,
    single_date: date | None,
    date_from: date | None,
    date_to: date | None,
    timezone_name: str,
) -> tuple[int | None, int | None]:
    if single_date is None and date_from is None and date_to is None:
        return None, None

    first_date = single_date or date_from
    last_date = single_date or date_to
    if first_date is None or last_date is None:
        raise ValueError("A complete calendar date window is required.")

    zone = parse_timezone(timezone_name)
    local_start = datetime.combine(first_date, time.min, tzinfo=zone)
    next_day = datetime.combine(last_date + timedelta(days=1), time.min, tzinfo=zone)
    local_end = next_day - timedelta(seconds=1)
    return (
        int(local_start.astimezone(timezone.utc).timestamp()),
        int(local_end.astimezone(timezone.utc).timestamp()),
    )


def parse_timezone(value: str) -> tzinfo:
    match = re.fullmatch(r"([+-])(\d{2}):(\d{2})", value)
    if match is None:
        return ZoneInfo(value)
    hours = int(match.group(2))
    minutes = int(match.group(3))
    if hours > 23 or minutes > 59:
        raise ValueError("Invalid fixed UTC offset.")
    delta = timedelta(hours=hours, minutes=minutes)
    if match.group(1) == "-":
        delta = -delta
    return timezone(delta)


__all__ = ["parse_timezone", "to_utc_window"]

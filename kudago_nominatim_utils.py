from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import Any


def clamp_int(value: int | str | None, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def csv_or_none(value: str | Iterable[str] | None) -> str | list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    items = [str(item).strip() for item in value if str(item).strip()]
    return items or None


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold().replace("ё", "е")
    value = re.sub(r"[^\w\s-]+", " ", value, flags=re.UNICODE)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def first_list_items(data: Any, *, limit: int = 5) -> list[dict[str, Any]]:
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict) and isinstance(data.get("results"), list):
        items = data["results"]
    else:
        return []
    return [item for item in items[:limit] if isinstance(item, dict)]


def status_error(tool: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"status": "error", "tool": tool, "message": message, **extra}


def status_ok(tool: str, data: Any, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": "ok", "tool": tool, **extra, "data": data}
    if isinstance(data, dict):
        if isinstance(data.get("results"), list):
            payload["count"] = data.get("count", len(data["results"]))
            payload["returned"] = len(data["results"])
        elif isinstance(data.get("id"), (int, str)):
            payload["object_id"] = data.get("id")
    elif isinstance(data, list):
        payload["count"] = len(data)
        payload["returned"] = len(data)
    return payload

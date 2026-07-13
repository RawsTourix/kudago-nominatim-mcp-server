from __future__ import annotations

import json
import re
from enum import StrEnum
from pathlib import Path
from typing import Any


SNAPSHOT_PATH = Path(__file__).with_name("kudago_v1_4.json")


def load_reference_snapshot() -> dict[str, Any]:
    payload = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    if payload.get("api_version") != "v1.4":
        raise RuntimeError("Unsupported KudaGo MCP reference snapshot version")
    for key in ("event_categories", "place_categories", "locations"):
        entries = payload.get(key)
        if not isinstance(entries, list) or not entries:
            raise RuntimeError(f"KudaGo MCP reference snapshot has no {key}")
    return payload


def _build_enum(name: str, entries: list[dict[str, Any]]) -> type[StrEnum]:
    members: dict[str, str] = {}
    for entry in entries:
        slug = entry.get("slug")
        if not isinstance(slug, str) or not slug:
            raise RuntimeError(f"KudaGo MCP reference {name} contains invalid slug")
        member = re.sub(r"[^A-Z0-9]+", "_", slug.upper()).strip("_")
        if not member or member[0].isdigit():
            member = f"VALUE_{member}"
        if member in members:
            raise RuntimeError(f"KudaGo MCP reference {name} has enum collision")
        members[member] = slug
    return StrEnum(name, members, module=__name__)


REFERENCE_SNAPSHOT = load_reference_snapshot()
EventCategory = _build_enum(
    "EventCategory",
    REFERENCE_SNAPSHOT["event_categories"],
)
PlaceCategory = _build_enum(
    "PlaceCategory",
    REFERENCE_SNAPSHOT["place_categories"],
)
KudaGoLocationSlug = _build_enum(
    "KudaGoLocationSlug",
    REFERENCE_SNAPSHOT["locations"],
)


def reference_timezone(
    *,
    location_slug: StrEnum | str | None = None,
    location_text: str | None = None,
) -> str | None:
    """Return the normalized timezone for an exact committed location match."""
    slug_value = (
        location_slug.value if isinstance(location_slug, StrEnum) else location_slug
    )
    slug_needle = _normalize_reference_text(slug_value)
    text_needle = _normalize_reference_text(location_text)
    for location in REFERENCE_SNAPSHOT["locations"]:
        slug = str(location.get("slug") or "")
        name = str(location.get("name") or "")
        if (
            slug_needle and _normalize_reference_text(slug) == slug_needle
        ) or (
            text_needle
            and text_needle
            in {_normalize_reference_text(slug), _normalize_reference_text(name)}
        ):
            timezone_name = location.get("timezone")
            return (
                normalize_reference_timezone(timezone_name)
                if isinstance(timezone_name, str)
                else None
            )
    return None


def normalize_reference_timezone(value: str) -> str:
    value = value.strip()
    match = re.fullmatch(r"GMT([+-]\d{2}:\d{2})", value, flags=re.IGNORECASE)
    return match.group(1) if match is not None else value


def _normalize_reference_text(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(value.casefold().replace("ё", "е").split())


__all__ = [
    "EventCategory",
    "KudaGoLocationSlug",
    "PlaceCategory",
    "REFERENCE_SNAPSHOT",
    "SNAPSHOT_PATH",
    "load_reference_snapshot",
    "normalize_reference_timezone",
    "reference_timezone",
]

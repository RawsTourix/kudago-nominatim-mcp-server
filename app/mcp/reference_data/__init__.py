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


__all__ = [
    "EventCategory",
    "KudaGoLocationSlug",
    "PlaceCategory",
    "REFERENCE_SNAPSHOT",
    "SNAPSHOT_PATH",
    "load_reference_snapshot",
]

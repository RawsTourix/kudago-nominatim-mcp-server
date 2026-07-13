from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.application.contracts import CommandOutput


REMOVED_DETAIL_FIELDS = {
    "body",
    "body_html",
    "images",
    "poster",
    "raw_response",
}


def serialize_details(output: CommandOutput) -> dict[str, Any]:
    payload = output.result_payload
    item_type = payload.get("object_type")
    if item_type == "list":
        item_type = "guide"
    result = {
        "status": output.status,
        "item_type": item_type,
        "item_id": payload.get("object_id"),
        "data": _compact_value(payload.get("data")),
    }
    if payload.get("comments") is not None:
        result["comments"] = _compact_value(payload["comments"])
    if payload.get("showings") is not None:
        result["showings"] = _compact_value(payload["showings"])
    return result


def _compact_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_compact_value(item) for item in value]
    if not isinstance(value, dict):
        if isinstance(value, str) and len(value) > 12_000:
            return value[:12_000] + "…"
        return deepcopy(value)
    return {
        key: _compact_value(item)
        for key, item in value.items()
        if key not in REMOVED_DETAIL_FIELDS
    }


__all__ = ["serialize_details"]

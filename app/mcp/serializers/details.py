from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.application.contracts import CommandOutput
from app.mcp.serializers.common import DETAIL_RESPONSE_LIMIT_BYTES, json_size


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
    return _enforce_detail_limit(result)


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


def _enforce_detail_limit(
    result: dict[str, Any],
    *,
    maximum_bytes: int = DETAIL_RESPONSE_LIMIT_BYTES,
) -> dict[str, Any]:
    truncated_sections: list[str] = []
    for key in ("comments", "showings"):
        values = result.get(key)
        if not isinstance(values, list):
            continue
        original_length = len(values)
        while values and json_size(result) > maximum_bytes:
            values.pop()
        if len(values) != original_length:
            truncated_sections.append(key)
            result[f"returned_{key}"] = len(values)
            result["truncated"] = True
            result["full_result_available"] = True

    if json_size(result) > maximum_bytes:
        data = result.get("data")
        result["data"] = _detail_summary(data)
        truncated_sections.append("data")
        result["truncated"] = True
        result["full_result_available"] = True

    if json_size(result) > maximum_bytes:
        for key in ("comments", "showings"):
            if key in result:
                result.pop(key)
                truncated_sections.append(key)

    if json_size(result) > maximum_bytes:
        result["data"] = None

    if truncated_sections:
        result["truncated_sections"] = list(dict.fromkeys(truncated_sections))
    return result


def _detail_summary(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        key: _compact_value(value[key])
        for key in (
            "id",
            "title",
            "short_title",
            "name",
            "description",
            "site_url",
            "address",
            "datetime",
        )
        if key in value and value[key] is not None
    }


__all__ = ["serialize_details"]

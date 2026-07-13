from typing import Any
from uuid import UUID


def mcp_ok(
    *,
    tool: str,
    job_id: UUID,
    data: Any,
    result_status: str = "ok",
    geo: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": "ok",
        "tool": tool,
        "job_id": str(job_id),
        "result_status": result_status,
        "geo": geo,
        "data": data,
        "meta": meta or {},
    }


def mcp_error(
    *,
    tool: str,
    message: str,
    error_type: str,
    job_id: UUID | None = None,
    details: list[dict[str, Any]] | None = None,
    retryable: bool | None = None,
) -> dict[str, Any]:
    result = {
        "status": "error",
        "tool": tool,
        "job_id": str(job_id) if job_id is not None else None,
        "message": message,
        "error_type": error_type,
    }
    if details is not None:
        result["details"] = details
    if retryable is not None:
        result["retryable"] = retryable
    return result


def mcp_validation_error(
    *,
    tool: str,
    error: Any,
) -> dict[str, Any]:
    details: list[dict[str, Any]] = []
    for item in error.errors(include_url=False):
        message = str(item.get("msg") or "Invalid value.")
        location = item.get("loc") or ()
        field = ".".join(str(part) for part in location) or _field_from_message(message)
        details.append(
            {
                "field": field,
                "code": _validation_code(str(item.get("type") or ""), message),
                "message": message,
            }
        )
    return mcp_error(
        tool=tool,
        message="Invalid tool arguments.",
        error_type="validation_error",
        details=details,
        retryable=True,
    )


def _field_from_message(message: str) -> str:
    lowered = message.lower()
    for field in (
        "radius_km",
        "coordinates",
        "location_slug",
        "place",
        "city",
        "date_from",
        "date_to",
        "date",
        "timezone",
        "departure_time",
        "arrival_time",
        "origin",
        "destination",
        "include_comments",
        "include_showings",
    ):
        if field in lowered:
            return field
    return "arguments"


def _validation_code(error_type: str, message: str) -> str:
    lowered = message.lower()
    if "required" in lowered or "provided together" in lowered:
        return "missing_required_companion"
    if "cannot be combined" in lowered or "exactly one" in lowered:
        return "invalid_combination"
    if "must be different" in lowered:
        return "identical_values"
    if error_type:
        return error_type.replace(".", "_")
    return "invalid_value"

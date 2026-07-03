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
) -> dict[str, Any]:
    return {
        "status": "error",
        "tool": tool,
        "job_id": str(job_id) if job_id is not None else None,
        "message": message,
        "error_type": error_type,
    }

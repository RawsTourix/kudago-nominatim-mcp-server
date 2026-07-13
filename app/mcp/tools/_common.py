from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from app.mcp.envelopes import mcp_validation_error


READ_ONLY_TOOL_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
}
MCP_FACADE_VERSION = "2"


def validation_error(tool_name: str, error: Any) -> dict[str, Any]:
    return mcp_validation_error(tool=tool_name, error=error)


def agent_filters(**values: Any) -> dict[str, Any]:
    return {
        key: _public_value(value)
        for key, value in values.items()
        if value is not None
    }


def _public_value(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_public_value(item) for item in value]
    return value


__all__ = [
    "MCP_FACADE_VERSION",
    "READ_ONLY_TOOL_ANNOTATIONS",
    "agent_filters",
    "validation_error",
]

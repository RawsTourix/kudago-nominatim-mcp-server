from __future__ import annotations

from typing import Any

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


__all__ = [
    "MCP_FACADE_VERSION",
    "READ_ONLY_TOOL_ANNOTATIONS",
    "validation_error",
]

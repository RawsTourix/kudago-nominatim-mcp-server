from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP
from pydantic import ValidationError

from app.mcp.executor import run_mcp_command
from app.mcp.schemas.details import (
    DetailItemType,
    GetDetailsInput,
    IncludeCommentsInput,
    IncludeShowingsInput,
    ItemIdInput,
    ItemTypeInput,
)
from app.mcp.serializers import serialize_details
from app.mcp.tools._common import (
    MCP_FACADE_VERSION,
    READ_ONLY_TOOL_ANNOTATIONS,
    validation_error,
)
from app.schemas.read_tools import ObjectDetailRequest


def register_details_tools(mcp: FastMCP) -> None:
    @mcp.tool(
        name="get_details",
        annotations=READ_ONLY_TOOL_ANNOTATIONS,
        version=MCP_FACADE_VERSION,
    )
    async def get_details(
        ctx: Context,
        item_type: ItemTypeInput,
        item_id: ItemIdInput,
        include_comments: IncludeCommentsInput = False,
        include_showings: IncludeShowingsInput = False,
    ) -> dict[str, Any]:
        """Get detailed information for an item returned by another KudaGo MCP tool.

        Use the exact item_type and item_id from details_ref. Showings are valid only for movies; comments are available only for supported item types.
        """
        tool_name = "get_details"
        try:
            agent_request = GetDetailsInput(
                item_type=item_type,
                item_id=item_id,
                include_comments=include_comments,
                include_showings=include_showings,
            )
            object_type = (
                "list"
                if agent_request.item_type == DetailItemType.GUIDE
                else agent_request.item_type.value
            )
            request = ObjectDetailRequest(
                object_type=object_type,
                object_id=agent_request.item_id,
                include_comments=agent_request.include_comments,
                include_showings=agent_request.include_showings,
                lang="ru",
            )
        except ValidationError as exc:
            return validation_error(tool_name, exc)

        return await run_mcp_command(
            redis=ctx.lifespan_context["arq_redis"],
            tool_name=tool_name,
            endpoint="mcp://tools/get_details",
            command="object.detail",
            payload=request.model_dump(),
            request_text=f"{agent_request.item_type.value}:{agent_request.item_id}",
            data_factory=serialize_details,
        )


__all__ = ["register_details_tools"]

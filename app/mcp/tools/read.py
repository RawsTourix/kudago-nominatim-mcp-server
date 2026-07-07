from typing import Annotated, Any

from fastmcp import FastMCP
from pydantic import Field, ValidationError

from app.mcp.envelopes import mcp_error
from app.mcp.executor import run_mcp_command
from app.schemas.read_tools import (
    ObjectDetailRequest,
    ReferenceGetRequest,
    ReferenceKind,
)


def register_read_tools(mcp: FastMCP) -> None:
    @mcp.tool(name="reference")
    async def reference(
        kind: Annotated[
            ReferenceKind,
            Field(
                description=(
                    "Reference kind. Use locations for official KudaGo slugs; "
                    "this is not the complete set of searchable places."
                )
            ),
        ],
        slug: str | None = None,
        lang: str = "ru",
    ) -> dict[str, Any]:
        """Read KudaGo categories and location references.

        kind must be event_categories, place_categories, locations, or
        location. For kind=location, provide a KudaGo slug such as msk.

        locations returns only official KudaGo location slugs, not a complete
        whitelist of supported cities. Do not restrict the user to that list.
        For another city, town, district, address, or landmark, pass its name
        as place_query to events or places; they check KudaGo first and fall
        back to Nominatim when needed.
        """
        tool_name = "reference"
        try:
            request = ReferenceGetRequest(kind=kind, slug=slug, lang=lang)
        except ValidationError as exc:
            return mcp_error(
                tool=tool_name,
                message=str(exc),
                error_type=exc.__class__.__name__,
            )

        return await run_mcp_command(
            tool_name=tool_name,
            endpoint="mcp://tools/reference",
            command="reference.get",
            payload=request.model_dump(),
            request_text=request.slug or request.kind,
        )

    @mcp.tool(name="object")
    async def object_detail(
        object_type: str,
        object_id: str,
        include_comments: bool = False,
        include_showings: bool = False,
        lang: str = "ru",
    ) -> dict[str, Any]:
        """Read a detailed KudaGo object by type and identifier.

        Supported types: event, place, movie, movie_showing, news, list,
        agent, agent_role, and location. Comments are available for selected
        object types; movie showings can be included for movie objects.
        """
        tool_name = "object"
        try:
            request = ObjectDetailRequest(
                object_type=object_type,
                object_id=object_id,
                include_comments=include_comments,
                include_showings=include_showings,
                lang=lang,
            )
        except ValidationError as exc:
            return mcp_error(
                tool=tool_name,
                message=str(exc),
                error_type=exc.__class__.__name__,
            )

        return await run_mcp_command(
            tool_name=tool_name,
            endpoint="mcp://tools/object",
            command="object.detail",
            payload=request.model_dump(),
            request_text=f"{request.object_type}:{request.object_id}",
        )

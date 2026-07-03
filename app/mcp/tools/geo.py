from typing import Any

from fastmcp import FastMCP
from pydantic import ValidationError

from app.application.contracts import CommandOutput
from app.mcp.envelopes import mcp_error
from app.mcp.executor import run_mcp_command
from app.schemas.geo import GeoResolveRequest


def _geo_payload(output: CommandOutput) -> dict[str, Any]:
    return {
        "status": output.status,
        "source": output.result_payload.get("source"),
        "query": output.result_payload.get("query"),
        "candidates": output.result_payload.get("candidates", []),
        "selected_lat": output.result_payload.get("selected_lat"),
        "selected_lon": output.result_payload.get("selected_lon"),
        "radius": output.result_payload.get("radius"),
    }


def register_geo_tools(mcp: FastMCP) -> None:
    @mcp.tool(name="resolve_place")
    async def resolve_place(
        query: str,
        countrycodes: str | None = "ru",
        limit: int = 5,
        accept_language: str | None = "ru",
    ) -> dict[str, Any]:
        """Geocode a place with Nominatim and return candidates with coordinates.

        Use this when a user supplied a city, district, address, landmark, or
        another free-form place. Multiple candidates mean the place is
        ambiguous and the user should clarify it.
        """
        tool_name = "resolve_place"
        try:
            request = GeoResolveRequest(
                query=query,
                countrycodes=countrycodes,
                limit=limit,
                accept_language=accept_language,
            )
        except ValidationError as exc:
            return mcp_error(
                tool=tool_name,
                message=str(exc),
                error_type=exc.__class__.__name__,
            )

        return await run_mcp_command(
            tool_name=tool_name,
            endpoint="mcp://tools/resolve_place",
            command="geo.resolve",
            payload=request.model_dump(),
            request_text=request.query,
            geo_factory=_geo_payload,
        )

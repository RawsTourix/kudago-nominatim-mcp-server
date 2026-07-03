from typing import Any

from fastmcp import FastMCP
from pydantic import ValidationError

from app.application.executor import CommandExecutor
from app.core.db import AsyncSessionLocal
from app.mcp.envelopes import mcp_error, mcp_ok
from app.schemas.geo import GeoResolveRequest
from app.services.job_service import JobService


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

        payload = request.model_dump()
        job = None

        async with AsyncSessionLocal() as session:
            try:
                job_service = JobService(session)
                job = await job_service.create_job_from_request(
                    endpoint="mcp://tools/resolve_place",
                    method="MCP",
                    command="geo.resolve",
                    input_payload=payload,
                    request_text=request.query,
                )
                output = await CommandExecutor(session).run_payload(
                    job_id=job.id,
                    command="geo.resolve",
                    payload=payload,
                    source="mcp",
                    endpoint="mcp://tools/resolve_place",
                )
                await session.commit()
            except Exception as exc:
                if job is None:
                    await session.rollback()
                else:
                    # CommandExecutor records the failed state and diagnostics.
                    # Commit them instead of erasing the MCP execution history.
                    await session.commit()
                return mcp_error(
                    tool=tool_name,
                    message=str(exc),
                    error_type=exc.__class__.__name__,
                    job_id=job.id if job is not None else None,
                )

        assert job is not None
        return mcp_ok(
            tool=tool_name,
            job_id=job.id,
            data=output.result_payload,
            result_status=output.status,
            geo={
                "status": output.status,
                "source": output.result_payload.get("source"),
                "query": output.result_payload.get("query"),
                "candidates": output.result_payload.get("candidates", []),
                "selected_lat": output.result_payload.get("selected_lat"),
                "selected_lon": output.result_payload.get("selected_lon"),
                "radius": output.result_payload.get("radius"),
            },
        )

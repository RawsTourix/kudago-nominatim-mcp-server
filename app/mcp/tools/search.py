from typing import Any

from fastmcp import FastMCP
from pydantic import ValidationError

from app.application.executor import CommandExecutor
from app.core.db import AsyncSessionLocal
from app.mcp.envelopes import mcp_error, mcp_ok
from app.schemas.events import EventsSearchRequest
from app.services.job_service import JobService


def register_search_tools(mcp: FastMCP) -> None:
    @mcp.tool(name="events")
    async def events(
        location: str | None = None,
        place_query: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        radius: int | None = None,
        actual_since: str | int | None = None,
        actual_until: str | int | None = None,
        categories: str | None = None,
        tags: str | None = None,
        is_free: bool | None = None,
        include_past: bool = False,
        page: int = 1,
        page_size: int = 10,
        lang: str | None = "ru",
    ) -> dict[str, Any]:
        """Search KudaGo events using deterministic filters.

        Use this for events filtered by a KudaGo location, a free-form place,
        coordinates and radius, dates, categories, tags, or free admission.
        Use location for a known KudaGo slug such as msk, or place_query for a
        city, district, address, or landmark that needs resolution.
        """
        tool_name = "events"
        try:
            request = EventsSearchRequest(
                location=location,
                place_query=place_query,
                lat=lat,
                lon=lon,
                radius=radius,
                actual_since=actual_since,
                actual_until=actual_until,
                categories=categories,
                tags=tags,
                is_free=is_free,
                include_past=include_past,
                page=page,
                page_size=page_size,
                lang=lang,
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
                job = await JobService(session).create_job_from_request(
                    endpoint="mcp://tools/events",
                    method="MCP",
                    command="events.search",
                    input_payload=payload,
                    request_text=request.place_query or request.location,
                )
                output = await CommandExecutor(session).run_payload(
                    job_id=job.id,
                    command="events.search",
                    payload=payload,
                    source="mcp",
                    endpoint="mcp://tools/events",
                )
                await session.commit()
            except Exception as exc:
                if job is None:
                    await session.rollback()
                else:
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
            geo=output.result_payload.get("geo"),
            meta=output.meta,
        )

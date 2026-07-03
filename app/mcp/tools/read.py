from typing import Any

from fastmcp import FastMCP
from pydantic import ValidationError

from app.application.executor import CommandExecutor
from app.core.db import AsyncSessionLocal
from app.mcp.envelopes import mcp_error, mcp_ok
from app.schemas.read_tools import ObjectDetailRequest, ReferenceGetRequest
from app.services.job_service import JobService


def register_read_tools(mcp: FastMCP) -> None:
    @mcp.tool(name="reference")
    async def reference(
        kind: str,
        slug: str | None = None,
        lang: str = "ru",
    ) -> dict[str, Any]:
        """Read KudaGo categories and location references.

        kind must be event_categories, place_categories, locations, or
        location. For kind=location, provide a KudaGo slug such as msk.
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

        payload = request.model_dump()
        job = None
        async with AsyncSessionLocal() as session:
            try:
                job = await JobService(session).create_job_from_request(
                    endpoint="mcp://tools/reference",
                    method="MCP",
                    command="reference.get",
                    input_payload=payload,
                    request_text=request.slug or request.kind,
                )
                output = await CommandExecutor(session).run_payload(
                    job_id=job.id,
                    command="reference.get",
                    payload=payload,
                    source="mcp",
                    endpoint="mcp://tools/reference",
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
            meta=output.meta,
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

        payload = request.model_dump()
        job = None
        async with AsyncSessionLocal() as session:
            try:
                job = await JobService(session).create_job_from_request(
                    endpoint="mcp://tools/object",
                    method="MCP",
                    command="object.detail",
                    input_payload=payload,
                    request_text=f"{request.object_type}:{request.object_id}",
                )
                output = await CommandExecutor(session).run_payload(
                    job_id=job.id,
                    command="object.detail",
                    payload=payload,
                    source="mcp",
                    endpoint="mcp://tools/object",
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
            meta=output.meta,
        )

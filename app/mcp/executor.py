from collections.abc import Callable
from typing import Any

from app.application.contracts import CommandOutput
from app.application.executor import CommandExecutor
from app.core.db import AsyncSessionLocal
from app.mcp.envelopes import mcp_error, mcp_ok
from app.services.job_service import JobService


async def run_mcp_command(
    *,
    tool_name: str,
    endpoint: str,
    command: str,
    payload: dict[str, Any],
    request_text: str | None = None,
    geo_factory: Callable[[CommandOutput], dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """Execute a command inline while preserving the complete MCP job history."""
    job = None

    async with AsyncSessionLocal() as session:
        try:
            job = await JobService(session).create_job_from_request(
                endpoint=endpoint,
                method="MCP",
                command=command,
                input_payload=payload,
                request_text=request_text,
            )
            output = await CommandExecutor(session).run_payload(
                job_id=job.id,
                command=command,
                payload=payload,
                source="mcp",
                endpoint=endpoint,
            )
            await session.commit()
        except Exception as exc:
            if job is None:
                await session.rollback()
            else:
                # CommandExecutor records failure diagnostics in this transaction.
                await session.commit()
            return mcp_error(
                tool=tool_name,
                message=str(exc),
                error_type=exc.__class__.__name__,
                job_id=job.id if job is not None else None,
            )

    assert job is not None
    geo = (
        geo_factory(output)
        if geo_factory is not None
        else output.result_payload.get("geo")
    )
    return mcp_ok(
        tool=tool_name,
        job_id=job.id,
        data=output.result_payload,
        result_status=output.status,
        geo=geo,
        meta=output.meta,
    )

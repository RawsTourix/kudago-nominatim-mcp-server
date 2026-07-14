import logging
from collections.abc import Callable
from typing import Any

from arq.connections import ArqRedis

from app.application.contracts import CommandOutput
from app.application.executor import CommandExecutor
from app.core.db import AsyncSessionLocal
from app.mcp.envelopes import mcp_error, mcp_ok
from app.mcp.normalization import compact_geo, compact_mcp_data, compact_mcp_meta
from app.services.job_dispatch_service import JobDispatchService
from app.services.job_service import JobService

logger = logging.getLogger(__name__)


async def run_mcp_command(
    *,
    redis: ArqRedis,
    tool_name: str,
    endpoint: str,
    command: str,
    payload: dict[str, Any],
    wait_timeout_seconds: float,
    request_text: str | None = None,
    geo_factory: Callable[[CommandOutput], dict[str, Any] | None] | None = None,
    data_factory: Callable[[CommandOutput], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Queue a command, await its worker result, and serialize persisted output."""
    async with AsyncSessionLocal() as session:
        try:
            dispatched = await JobDispatchService(
                session,
                redis,
            ).create_and_enqueue(
                endpoint=endpoint,
                method="MCP",
                command=command,
                input_payload=payload,
                request_text=request_text,
            )
        except Exception as exc:
            return mcp_error(
                tool=tool_name,
                message=str(exc),
                error_type=exc.__class__.__name__,
                job_id=getattr(exc, "job_id", None),
                retryable=False,
            )

    try:
        await dispatched.arq_job.result(
            timeout=wait_timeout_seconds,
        )
    except TimeoutError as exc:
        async with AsyncSessionLocal() as session:
            job = await JobService(session).get_by_id(dispatched.job.id)

        if job is not None and job.status == "failed":
            return mcp_error(
                tool=tool_name,
                job_id=job.id,
                error_type=job.error_type or exc.__class__.__name__,
                message=job.error_message or str(exc),
                retryable=False,
            )
        return mcp_error(
            tool=tool_name,
            job_id=dispatched.job.id,
            error_type="processing_timeout",
            message=(
                "The job is still queued or running and did not finish within "
                "the MCP wait timeout."
            ),
            retryable=False,
        )
    except Exception as exc:
        async with AsyncSessionLocal() as session:
            job = await JobService(session).get_by_id(dispatched.job.id)

        if job is not None and job.status == "failed":
            return mcp_error(
                tool=tool_name,
                job_id=job.id,
                error_type=job.error_type or exc.__class__.__name__,
                message=job.error_message or str(exc),
                retryable=False,
            )
        return mcp_error(
            tool=tool_name,
            job_id=dispatched.job.id,
            error_type=exc.__class__.__name__,
            message=str(exc),
            retryable=False,
        )

    try:
        async with AsyncSessionLocal() as session:
            output = await CommandExecutor(session).load_completed_output(
                dispatched.job.id
            )
    except Exception as exc:
        return mcp_error(
            tool=tool_name,
            job_id=dispatched.job.id,
            error_type=exc.__class__.__name__,
            message=str(exc),
            retryable=False,
        )

    geo = (
        geo_factory(output)
        if geo_factory is not None
        else output.result_payload.get("geo")
    )
    try:
        data = (
            data_factory(output)
            if data_factory is not None
            else compact_mcp_data(output.result_payload)
        )
        return mcp_ok(
            tool=tool_name,
            job_id=dispatched.job.id,
            data=data,
            result_status=output.status,
            geo=compact_geo(geo),
            meta=compact_mcp_meta(output.meta),
        )
    except Exception as exc:
        logger.exception(
            "MCP serialization failed: tool=%s job_id=%s command=%s",
            tool_name,
            dispatched.job.id,
            command,
        )
        return mcp_error(
            tool=tool_name,
            message="The complete result was saved, but MCP serialization failed.",
            error_type=exc.__class__.__name__,
            job_id=dispatched.job.id,
            retryable=False,
        )

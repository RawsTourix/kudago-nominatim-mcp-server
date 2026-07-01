import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.upstream_call import UpstreamCall


class UpstreamCallRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        job_id: uuid.UUID,
        provider: str,
        operation: str,
        success: bool,
        url_path: str | None = None,
        request_payload: dict[str, Any] | None = None,
        response_payload: dict[str, Any] | list[Any] | None = None,
        response_status_code: int | None = None,
        duration_ms: int | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> UpstreamCall:
        call = UpstreamCall(
            job_id=job_id,
            provider=provider,
            operation=operation,
            url_path=url_path,
            request_payload=request_payload,
            response_payload=response_payload,
            response_status_code=response_status_code,
            duration_ms=duration_ms,
            success=success,
            error_type=error_type,
            error_message=error_message,
        )
        self.session.add(call)
        await self.session.flush()
        return call

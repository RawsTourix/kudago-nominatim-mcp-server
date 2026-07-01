import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.command_result import CommandResult


class ResultRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        job_id: uuid.UUID,
        result_type: str,
        items: list[dict[str, Any]],
        meta: dict[str, Any] | None = None,
    ) -> CommandResult:
        result = CommandResult(
            job_id=job_id,
            result_type=result_type,
            items=items,
            meta=meta or {},
        )
        self.session.add(result)
        await self.session.flush()
        return result
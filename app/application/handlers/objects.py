from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.contracts import CommandOutput, ExecutionContext
from app.core.config import settings
from app.services.object_service import ObjectService


class ObjectDetailHandler:
    command = "object.detail"

    def __init__(self, session: AsyncSession):
        self.object_service = ObjectService(session)

    async def run(
        self,
        context: ExecutionContext,
        payload: dict[str, Any],
    ) -> CommandOutput:
        object_type = str(payload.get("object_type") or "").strip().lower()
        object_id = str(payload.get("object_id") or "").strip()
        if not object_id:
            raise ValueError("object_id must not be empty")

        result = await self.object_service.get_object_detail(
            object_type=object_type,
            object_id=object_id,
            include_comments=payload.get("include_comments", False),
            include_showings=payload.get("include_showings", False),
            lang=payload.get("lang") or settings.kudago_lang,
            job_id=context.job_id,
        )
        data = result.get("data")
        items = [data] if isinstance(data, dict) else []
        return CommandOutput(
            status=str(result.get("status", "ok")),
            result_type=self.command,
            items=items,
            meta={
                "status": result.get("status", "ok"),
                "object_type": result.get("object_type"),
                "object_id": result.get("object_id"),
                "comments_included": result.get("comments") is not None,
                "showings_included": result.get("showings") is not None,
            },
            result_payload=result,
        )

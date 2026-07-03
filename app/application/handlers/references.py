from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.contracts import CommandOutput, ExecutionContext
from app.core.config import settings
from app.services.reference_service import ReferenceService


class ReferenceHandler:
    command = "reference.get"

    def __init__(self, session: AsyncSession):
        self.reference_service = ReferenceService(session)

    async def run(
        self,
        context: ExecutionContext,
        payload: dict[str, Any],
    ) -> CommandOutput:
        kind = str(payload.get("kind") or "").strip().lower()
        lang = payload.get("lang") or settings.kudago_lang

        if kind == "event_categories":
            result = await self.reference_service.get_event_categories(
                lang=lang,
                job_id=context.job_id,
            )
        elif kind == "place_categories":
            result = await self.reference_service.get_place_categories(
                lang=lang,
                job_id=context.job_id,
            )
        elif kind == "locations":
            result = await self.reference_service.get_locations(
                lang=lang,
                job_id=context.job_id,
            )
        elif kind == "location":
            slug = payload.get("slug")
            if not slug:
                raise ValueError("slug is required for kind=location")
            result = await self.reference_service.get_location(
                slug=slug,
                lang=lang,
                job_id=context.job_id,
            )
        else:
            raise ValueError(f"Unsupported reference kind: {kind}")

        data = result.get("data")
        items = self._result_items(data)
        return CommandOutput(
            status=str(result.get("status", "ok")),
            result_type=self.command,
            items=items,
            meta={
                "status": result.get("status", "ok"),
                "kind": kind,
                "slug": result.get("slug"),
            },
            result_payload=result,
        )

    @staticmethod
    def _result_items(data: Any) -> list[dict[str, Any]]:
        if isinstance(data, dict):
            return [data]
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return []

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.contracts import CommandOutput, ExecutionContext
from app.services.geo_service import GeoService


class GeoResolveHandler:
    command = "geo.resolve"

    def __init__(self, session: AsyncSession):
        self.geo_service = GeoService(session)

    async def run(
        self,
        context: ExecutionContext,
        payload: dict[str, Any],
    ) -> CommandOutput:
        result_payload = await self.geo_service.resolve_place(
            job_id=context.job_id,
            query=payload["query"],
            countrycodes=payload.get("countrycodes", "ru"),
            limit=payload.get("limit", 5),
            accept_language=payload.get("accept_language", "ru"),
        )
        candidates = result_payload.get("candidates", [])

        return CommandOutput(
            status=result_payload["status"],
            result_type=self.command,
            items=candidates,
            meta={
                "status": result_payload["status"],
                "source": result_payload["source"],
                "query": result_payload["query"],
                "selected_lat": result_payload.get("selected_lat"),
                "selected_lon": result_payload.get("selected_lon"),
                "radius": result_payload.get("radius"),
            },
            result_payload=result_payload,
        )

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.contracts import CommandOutput, ExecutionContext
from app.core.config import settings
from app.services.events_service import EventsService
from app.services.location_resolver_service import LocationResolverService


class EventsSearchHandler:
    command = "events.search"

    def __init__(self, session: AsyncSession):
        self.events_service = EventsService(session)
        self.location_resolver = LocationResolverService(session)

    async def run(
        self,
        context: ExecutionContext,
        payload: dict[str, Any],
    ) -> CommandOutput:
        lang = payload.get("lang") or settings.kudago_lang
        resolved = (
            await self.location_resolver.resolve_for_kudago_location_or_coordinates(
                job_id=context.job_id,
                place_query=payload.get("place_query"),
                location=payload.get("location"),
                lat=payload.get("lat"),
                lon=payload.get("lon"),
                radius=payload.get("radius"),
                lang=lang,
                allow_coordinates=True,
            )
        )
        geo_meta = resolved["geo"]

        if resolved["status"] != "ok":
            result_status = resolved["status"]
            result_payload = {
                "status": result_status,
                "message": "Geo resolution did not produce a usable result",
                "geo": geo_meta,
                "items": [],
                "count": 0,
                "returned": 0,
            }
            return CommandOutput(
                status=result_status,
                result_type=self.command,
                items=[],
                meta={"status": result_status, "geo": geo_meta},
                result_payload=result_payload,
            )

        actual_since = payload.get("actual_since")
        actual_until = payload.get("actual_until")
        include_past = payload.get("include_past", False)
        if actual_since is None and not include_past:
            actual_since = int(datetime.now(timezone.utc).timestamp())

        filters = {
            "actual_since": actual_since,
            "actual_until": actual_until,
            "include_past": include_past,
            "categories": payload.get("categories"),
            "tags": payload.get("tags"),
            "is_free": payload.get("is_free"),
        }
        search_result = await self.events_service.search_events(
            job_id=context.job_id,
            location=resolved["location"],
            lat=resolved["lat"],
            lon=resolved["lon"],
            radius=resolved["radius"],
            actual_since=actual_since,
            actual_until=actual_until,
            categories=payload.get("categories"),
            tags=payload.get("tags"),
            is_free=payload.get("is_free"),
            page=payload.get("page", 1),
            page_size=payload.get("page_size", 10),
            lang=lang,
        )
        items = search_result["items"]
        result_payload = {
            "status": "ok",
            "source": "kudago",
            "geo": geo_meta,
            "filters": filters,
            "count": search_result.get("count"),
            "returned": search_result.get("returned"),
            "items": items,
        }
        return CommandOutput(
            status="ok",
            result_type=self.command,
            items=items,
            meta={
                "status": "ok",
                "source": "kudago",
                "geo": geo_meta,
                "filters": filters,
                "count": search_result.get("count"),
                "returned": search_result.get("returned"),
            },
            result_payload=result_payload,
        )

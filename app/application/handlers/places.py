from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.contracts import CommandEvent, CommandOutput, ExecutionContext
from app.core.config import settings
from app.services.location_resolver_service import LocationResolverService
from app.services.places_service import PlacesService


class PlacesSearchHandler:
    command = "places.search"

    def __init__(self, session: AsyncSession):
        self.location_resolver = LocationResolverService(session)
        self.places_service = PlacesService(session)

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
                "message": self._geo_message(result_status),
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

        showing_since = payload.get("showing_since")
        showing_until = payload.get("showing_until")
        events: list[CommandEvent] = []
        if (
            payload.get("has_showings") is True
            and showing_since is None
            and showing_until is None
        ):
            now = datetime.now(timezone.utc)
            showing_since = int(now.timestamp())
            showing_until = int((now + timedelta(days=7)).timestamp())
            events.append(
                CommandEvent(
                    event_type="showing_window_defaulted",
                    message=(
                        "showing_since/showing_until were not provided, "
                        "defaulted to next 7 days"
                    ),
                    data={
                        "showing_since": showing_since,
                        "showing_until": showing_until,
                    },
                )
            )

        filters = {
            "categories": payload.get("categories"),
            "tags": payload.get("tags"),
            "has_showings": payload.get("has_showings"),
            "showing_since": showing_since,
            "showing_until": showing_until,
        }
        search_result = await self.places_service.search_places(
            job_id=context.job_id,
            location=resolved["location"],
            lat=resolved["lat"],
            lon=resolved["lon"],
            radius=resolved["radius"],
            categories=payload.get("categories"),
            tags=payload.get("tags"),
            has_showings=payload.get("has_showings"),
            showing_since=showing_since,
            showing_until=showing_until,
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
            events=events,
        )

    @staticmethod
    def _geo_message(status: str) -> str:
        if status == "geo_ambiguous":
            return (
                "Geo resolution is ambiguous; choose one candidate or pass "
                "coordinates."
            )
        return "Geo resolution did not find a matching place."

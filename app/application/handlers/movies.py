from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.contracts import CommandEvent, CommandOutput, ExecutionContext
from app.core.config import settings
from app.services.location_resolver_service import LocationResolverService
from app.services.movies_service import MoviesService


class MoviesSearchHandler:
    command = "movies.search"

    def __init__(self, session: AsyncSession):
        self.location_resolver = LocationResolverService(session)
        self.movies_service = MoviesService(session)

    async def run(
        self,
        context: ExecutionContext,
        payload: dict[str, Any],
    ) -> CommandOutput:
        lang = payload.get("lang") or settings.kudago_lang
        place_query = payload.get("place_query")
        resolved = (
            await self.location_resolver.resolve_for_kudago_location_or_coordinates(
                job_id=context.job_id,
                place_query=place_query,
                location=payload.get("location"),
                lat=None,
                lon=None,
                radius=None,
                lang=lang,
                allow_coordinates=False,
            )
        )

        if resolved["status"] != "ok":
            status = resolved["status"]
            result_payload = {
                "status": status,
                "message": self._geo_message(status),
                "geo": resolved["geo"],
                "items": [],
                "count": 0,
                "returned": 0,
            }
            return CommandOutput(
                status=status,
                result_type=self.command,
                items=[],
                meta={"status": status, "geo": resolved["geo"]},
                result_payload=result_payload,
            )

        actual_since = payload.get("actual_since")
        actual_until = payload.get("actual_until")
        include_past = payload.get("include_past", False)
        events: list[CommandEvent] = []
        if actual_since is None and not include_past:
            actual_since = int(datetime.now(timezone.utc).timestamp())
            events.append(
                CommandEvent(
                    event_type="actual_since_defaulted",
                    message=(
                        "actual_since was not provided, defaulted to current UTC "
                        "timestamp"
                    ),
                    data={"actual_since": actual_since},
                )
            )

        location = resolved["location"]
        filters = {
            "location": location,
            "place_query": place_query,
            "place_id": payload.get("place_id"),
            "tags": payload.get("tags"),
            "is_free": payload.get("is_free"),
            "premiering_in_location": payload.get("premiering_in_location"),
            "actual_since": actual_since,
            "actual_until": actual_until,
            "include_past": include_past,
        }
        search_result = await self.movies_service.search_movies(
            job_id=context.job_id,
            location=location,
            place_id=payload.get("place_id"),
            tags=payload.get("tags"),
            is_free=payload.get("is_free"),
            premiering_in_location=payload.get("premiering_in_location"),
            actual_since=actual_since,
            actual_until=actual_until,
            page=payload.get("page", 1),
            page_size=payload.get("page_size", 10),
            lang=lang,
        )
        items = search_result["items"]
        result_payload = {
            "status": "ok",
            "source": "kudago",
            "geo": resolved["geo"],
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
                "geo": resolved["geo"],
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
                "Geo resolution is ambiguous; specify a KudaGo location slug or "
                "place_id."
            )
        if status == "geo_not_found":
            return (
                "Geo resolution did not find a matching place; specify a KudaGo "
                "location slug or place_id."
            )
        return (
            "KudaGo movies endpoint requires a KudaGo location slug or place_id. "
            "Coordinates are not supported."
        )

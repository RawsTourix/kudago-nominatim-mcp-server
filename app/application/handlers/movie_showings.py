from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.contracts import CommandEvent, CommandOutput, ExecutionContext
from app.core.config import settings
from app.services.location_resolver_service import LocationResolverService
from app.services.movie_showings_service import MovieShowingsService


class MovieShowingsSearchHandler:
    command = "movie_showings.search"

    def __init__(self, session: AsyncSession):
        self.location_resolver = LocationResolverService(session)
        self.movie_showings_service = MovieShowingsService(session)

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
        events: list[CommandEvent] = []
        if actual_since is None and actual_until is None:
            now = datetime.now(timezone.utc)
            actual_since = int(now.timestamp())
            actual_until = int((now + timedelta(days=7)).timestamp())
            events.append(
                CommandEvent(
                    event_type="actual_window_defaulted",
                    message=(
                        "actual_since/actual_until were not provided, defaulted "
                        "to next 7 days"
                    ),
                    data={
                        "actual_since": actual_since,
                        "actual_until": actual_until,
                    },
                )
            )

        location = resolved["location"]
        filters = {
            "movie_id": payload.get("movie_id"),
            "location": location,
            "place_query": place_query,
            "place_id": payload.get("place_id"),
            "actual_since": actual_since,
            "actual_until": actual_until,
            "is_free": payload.get("is_free"),
        }
        search_result = await self.movie_showings_service.search_movie_showings(
            job_id=context.job_id,
            movie_id=payload.get("movie_id"),
            location=location,
            actual_since=actual_since,
            actual_until=actual_until,
            place_id=payload.get("place_id"),
            is_free=payload.get("is_free"),
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
            "KudaGo movie showings endpoint requires a KudaGo location slug or "
            "place_id. Coordinates are not supported."
        )

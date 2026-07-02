from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.events_service import EventsService
from app.services.geo_service import GeoService


class LocationResolverService:
    def __init__(self, session: AsyncSession):
        self.events_service = EventsService(session)
        self.geo_service = GeoService(session)

    async def resolve_for_kudago_location_or_coordinates(
        self,
        *,
        job_id: UUID,
        place_query: str | None,
        location: str | None,
        lat: float | None,
        lon: float | None,
        radius: int | None,
        lang: str,
        allow_coordinates: bool,
    ) -> dict[str, Any]:
        if location:
            return {
                "status": "ok",
                "location": location,
                "lat": lat,
                "lon": lon,
                "radius": radius,
                "geo": {
                    "status": "ok",
                    "kind": "kudago_location",
                    "location": location,
                },
            }

        if lat is not None and lon is not None and radius is not None:
            if not allow_coordinates:
                return {
                    "status": "geo_unsupported",
                    "location": None,
                    "lat": None,
                    "lon": None,
                    "radius": None,
                    "geo": {
                        "status": "unsupported",
                        "kind": "coordinates",
                        "lat": lat,
                        "lon": lon,
                        "radius": radius,
                    },
                }

            return {
                "status": "ok",
                "location": None,
                "lat": lat,
                "lon": lon,
                "radius": radius,
                "geo": {
                    "status": "ok",
                    "kind": "coordinates",
                    "lat": lat,
                    "lon": lon,
                    "radius": radius,
                },
            }

        if not place_query:
            return {
                "status": "ok",
                "location": None,
                "lat": None,
                "lon": None,
                "radius": None,
                "geo": None,
            }

        matched_location = await self.events_service.find_kudago_location(
            job_id=job_id,
            place_query=place_query,
            lang=lang,
        )
        if matched_location is not None:
            resolved_location = matched_location.get("slug")
            return {
                "status": "ok",
                "location": resolved_location,
                "lat": None,
                "lon": None,
                "radius": None,
                "geo": {
                    "status": "ok",
                    "kind": "kudago_location",
                    "location": resolved_location,
                    "matched_location": matched_location,
                },
            }

        geo_result = await self.geo_service.resolve_place(
            job_id=job_id,
            query=place_query,
            countrycodes=settings.nominatim_countrycodes,
            limit=5,
            accept_language=lang,
        )
        if geo_result["status"] != "ok":
            return {
                "status": (
                    "geo_ambiguous"
                    if geo_result["status"] == "ambiguous"
                    else "geo_not_found"
                ),
                "location": None,
                "lat": None,
                "lon": None,
                "radius": None,
                "geo": {
                    "status": geo_result["status"],
                    "kind": "none",
                    "source": geo_result["source"],
                    "query": place_query,
                    "candidates": geo_result.get("candidates", []),
                    "selected_lat": geo_result.get("selected_lat"),
                    "selected_lon": geo_result.get("selected_lon"),
                    "radius": geo_result.get("radius"),
                },
            }

        resolved_radius = geo_result["radius"] or settings.default_radius
        if not allow_coordinates:
            return {
                "status": "geo_unsupported",
                "location": None,
                "lat": None,
                "lon": None,
                "radius": None,
                "geo": {
                    "status": geo_result["status"],
                    "kind": "coordinates",
                    "source": geo_result["source"],
                    "query": place_query,
                    "selected_lat": geo_result.get("selected_lat"),
                    "selected_lon": geo_result.get("selected_lon"),
                    "radius": resolved_radius,
                },
            }

        return {
            "status": "ok",
            "location": None,
            "lat": geo_result["selected_lat"],
            "lon": geo_result["selected_lon"],
            "radius": resolved_radius,
            "geo": {
                "status": "ok",
                "kind": "coordinates",
                "source": geo_result["source"],
                "query": place_query,
                "selected_lat": geo_result.get("selected_lat"),
                "selected_lon": geo_result.get("selected_lon"),
                "radius": resolved_radius,
            },
        }

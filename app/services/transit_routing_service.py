import time
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.integrations.transitous import (
    TransitousHttpClient,
    TransitousInvalidResponseError,
    TransitousResponseError,
    plan_journey,
)
from app.repositories.upstream_call_repository import UpstreamCallRepository
from app.schemas.routing import TransitMode, TransitRouteRequest


TRANSITOUS_ATTRIBUTION = [
    {
        "name": "Transitous data sources",
        "url": "https://transitous.org/sources/",
    },
    {
        "name": "OpenStreetMap contributors",
        "url": "https://www.openstreetmap.org/copyright",
    },
]


class TransitRoutingService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        client: TransitousHttpClient | None = None,
    ) -> None:
        self.upstream_call_repo = UpstreamCallRepository(session)
        self.client = client

    async def plan_route(
        self,
        *,
        job_id: UUID,
        request: TransitRouteRequest,
    ) -> dict[str, Any]:
        transit_modes = [
            mode.value
            for mode in (request.transit_modes or [TransitMode.TRANSIT])
        ]
        from_place = _coordinate_pair(request.origin_lat, request.origin_lon)
        to_place = _coordinate_pair(
            request.destination_lat,
            request.destination_lon,
        )
        request_payload = {
            "from_place": from_place,
            "to_place": to_place,
            "time": request.time.isoformat() if request.time else None,
            "arrive_by": request.arrive_by,
            "transit_modes": transit_modes,
            "max_transfers": request.max_transfers,
            "max_travel_time_minutes": request.max_travel_time_minutes,
            "min_transfer_time_minutes": request.min_transfer_time_minutes,
            "num_itineraries": request.num_itineraries,
            "search_window_seconds": request.search_window_seconds,
            "language": request.language,
        }
        client = self.client or TransitousHttpClient(
            base_url=settings.transitous_base_url,
            timeout=settings.transitous_timeout_seconds,
            user_agent=settings.transitous_user_agent,
            trust_env=True,
        )
        started = time.perf_counter()

        try:
            raw = await plan_journey(
                client,
                from_place=from_place,
                to_place=to_place,
                time=request.time,
                arrive_by=request.arrive_by,
                transit_modes=transit_modes,
                max_transfers=request.max_transfers,
                max_travel_time=request.max_travel_time_minutes,
                min_transfer_time=request.min_transfer_time_minutes,
                num_itineraries=request.num_itineraries,
                search_window=request.search_window_seconds,
                language=request.language,
            )
        except Exception as exc:
            await self.upstream_call_repo.create(
                job_id=job_id,
                provider="transitous",
                operation="plan",
                url_path="/api/v6/plan",
                request_payload=request_payload,
                response_payload=(
                    exc.response_payload
                    if isinstance(exc, TransitousResponseError)
                    else None
                ),
                response_status_code=(
                    exc.status_code
                    if isinstance(exc, TransitousResponseError)
                    else None
                ),
                duration_ms=_duration_ms(started),
                success=False,
                error_type=exc.__class__.__name__,
                error_message=str(exc),
            )
            if (
                isinstance(exc, TransitousResponseError)
                and 400 <= exc.status_code < 500
                and exc.status_code != 429
                and isinstance(exc.response_payload, dict)
                and _explicit_coverage_unavailable(exc.response_payload)
            ):
                return _coverage_unavailable_result(
                    request,
                    transit_modes,
                    _list_value(exc.response_payload.get("warnings")),
                )
            raise
        finally:
            if self.client is None:
                await client.aclose()

        try:
            result = self._normalize(raw, request, transit_modes)
        except Exception as exc:
            await self.upstream_call_repo.create(
                job_id=job_id,
                provider="transitous",
                operation="plan",
                url_path="/api/v6/plan",
                request_payload=request_payload,
                response_payload=raw,
                response_status_code=200,
                duration_ms=_duration_ms(started),
                success=False,
                error_type=exc.__class__.__name__,
                error_message=str(exc),
            )
            raise

        await self.upstream_call_repo.create(
            job_id=job_id,
            provider="transitous",
            operation="plan",
            url_path="/api/v6/plan",
            request_payload=request_payload,
            response_payload=raw,
            response_status_code=200,
            duration_ms=_duration_ms(started),
            success=True,
        )
        return result

    @staticmethod
    def _normalize(
        raw: dict[str, Any],
        request: TransitRouteRequest,
        transit_modes: list[str],
    ) -> dict[str, Any]:
        query = _transit_query(request, transit_modes)
        warnings = _list_value(raw.get("warnings"))

        if _explicit_coverage_unavailable(raw):
            return _coverage_unavailable_result(
                request,
                transit_modes,
                warnings,
            )

        itineraries = raw.get("itineraries")
        if not isinstance(itineraries, list):
            raise TransitousInvalidResponseError(
                "Transitous plan response does not contain an itineraries array"
            )

        routes = [
            _normalize_itinerary(itinerary)
            for itinerary in itineraries[: request.num_itineraries]
            if isinstance(itinerary, dict)
        ]
        if len(routes) != min(len(itineraries), request.num_itineraries):
            raise TransitousInvalidResponseError(
                "Transitous itineraries must be JSON objects"
            )

        if not routes:
            return {
                "status": "no_route",
                "provider": "transitous",
                "query": query,
                "returned": 0,
                "routes": [],
                "message": (
                    "No public transport route was found for the selected "
                    "points and time."
                ),
                "warnings": warnings,
                "attribution": TRANSITOUS_ATTRIBUTION,
            }

        return {
            "status": "ok",
            "provider": "transitous",
            "query": query,
            "returned": len(routes),
            "routes": routes,
            "warnings": warnings,
            "attribution": TRANSITOUS_ATTRIBUTION,
        }


def _transit_query(
    request: TransitRouteRequest,
    transit_modes: list[str],
) -> dict[str, Any]:
    return {
        "origin": {"lat": request.origin_lat, "lon": request.origin_lon},
        "destination": {
            "lat": request.destination_lat,
            "lon": request.destination_lon,
        },
        "time": request.time.isoformat() if request.time else None,
        "arrive_by": request.arrive_by,
        "transit_modes": transit_modes,
    }


def _normalize_itinerary(itinerary: dict[str, Any]) -> dict[str, Any]:
    raw_legs = itinerary.get("legs")
    if raw_legs is None:
        raw_legs = []
    if not isinstance(raw_legs, list) or not all(
        isinstance(leg, dict) for leg in raw_legs
    ):
        raise TransitousInvalidResponseError(
            "Transitous itinerary legs must be an array of objects"
        )

    legs = [_normalize_leg(leg) for leg in raw_legs]
    return {
        "departure_time": _iso_time(itinerary.get("startTime")),
        "arrival_time": _iso_time(itinerary.get("endTime")),
        "duration_seconds": _number(itinerary.get("duration")),
        "transfers": _integer(itinerary.get("transfers")),
        "has_realtime_data": any(leg.get("realtime") is True for leg in legs),
        "has_cancellations": any(
            leg.get("cancelled") is True for leg in legs
        ),
        "legs": legs,
    }


def _normalize_leg(leg: dict[str, Any]) -> dict[str, Any]:
    cancelled = _optional_bool(leg.get("cancelled"))
    if leg.get("tripCancelled") is True:
        cancelled = True
    return {
        "mode": _text(leg.get("mode")),
        "from": _normalize_place(leg.get("from")),
        "to": _normalize_place(leg.get("to")),
        "departure_time": _iso_time(leg.get("startTime")),
        "arrival_time": _iso_time(leg.get("endTime")),
        "scheduled_departure_time": _iso_time(leg.get("scheduledStartTime")),
        "scheduled_arrival_time": _iso_time(leg.get("scheduledEndTime")),
        "duration_seconds": _number(leg.get("duration")),
        "distance_meters": _number(leg.get("distance")),
        "route_short_name": _text(leg.get("routeShortName")),
        "route_long_name": _text(leg.get("routeLongName")),
        "headsign": _text(leg.get("headsign")),
        "agency_name": _text(leg.get("agencyName")),
        "realtime": _optional_bool(leg.get("realTime")),
        "cancelled": cancelled,
        "interline_with_previous_leg": _optional_bool(
            leg.get("interlineWithPreviousLeg")
        ),
    }


def _normalize_place(value: Any) -> dict[str, Any]:
    place = value if isinstance(value, dict) else {}
    return {
        "name": _text(place.get("name")),
        "lat": _number(place.get("lat")),
        "lon": _number(place.get("lon")),
    }


def _explicit_coverage_unavailable(raw: dict[str, Any]) -> bool:
    if raw.get("status") == "coverage_unavailable":
        return True
    error = raw.get("error")
    return isinstance(error, dict) and error.get("code") in {
        "NO_COVERAGE",
        "COVERAGE_UNAVAILABLE",
    }


def _coverage_unavailable_result(
    request: TransitRouteRequest,
    transit_modes: list[str],
    warnings: list[Any],
) -> dict[str, Any]:
    return {
        "status": "coverage_unavailable",
        "provider": "transitous",
        "query": _transit_query(request, transit_modes),
        "returned": 0,
        "routes": [],
        "message": (
            "Transitous reported that routing data is unavailable for the "
            "selected points."
        ),
        "warnings": warnings,
        "attribution": TRANSITOUS_ATTRIBUTION,
    }


def _coordinate_pair(lat: float, lon: float) -> str:
    return f"{lat},{lon}"


def _duration_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _iso_time(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TransitousInvalidResponseError(
            "Transitous time fields must be ISO 8601 strings"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TransitousInvalidResponseError(
            "Transitous returned an invalid ISO 8601 time"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TransitousInvalidResponseError(
            "Transitous time fields must include a timezone or UTC offset"
        )
    return value


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _integer(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None

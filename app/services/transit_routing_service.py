import json
import time
from collections.abc import Iterable
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

PROVIDER_MODE_NAMES = {
    "WALK": "walking",
    "BIKE": "cycling",
    "RENTAL": "rental",
    "CAR": "driving",
    "CAR_PARKING": "car_parking",
    "CAR_DROPOFF": "car_dropoff",
    "ODM": "on_demand_transport",
    "RIDE_SHARING": "ride_sharing",
    "FLEX": "flexible_transport",
    "TRANSIT": "transit",
    "TRAM": "tram",
    "SUBWAY": "subway",
    "FERRY": "ferry",
    "AIRPLANE": "airplane",
    "BUS": "bus",
    "COACH": "coach",
    "RAIL": "rail",
    "HIGHSPEED_RAIL": "high_speed_rail",
    "LONG_DISTANCE": "long_distance_rail",
    "NIGHT_RAIL": "night_rail",
    "REGIONAL_FAST_RAIL": "regional_fast_rail",
    "REGIONAL_RAIL": "regional_rail",
    "SUBURBAN": "suburban_rail",
    "FUNICULAR": "funicular",
    "AERIAL_LIFT": "aerial_lift",
    "OTHER": "other",
    "AREAL_LIFT": "aerial_lift",
    "METRO": "suburban_rail",
    "CABLE_CAR": "cable_car",
}
DEBUG_PROVIDER_MODES = {
    "DEBUG_BUS_ROUTE",
    "DEBUG_RAILWAY_ROUTE",
    "DEBUG_FERRY_ROUTE",
}

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
        transit_modes = _effective_transit_modes(request)
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
            "pre_transit_modes": ["WALK"],
            "post_transit_modes": ["WALK"],
            "direct_modes": [],
            "max_pre_transit_time": 900,
            "max_post_transit_time": 900,
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
                "warnings": [],
                "attribution": TRANSITOUS_ATTRIBUTION,
            }

        warnings = _deduplicate_warnings(
            warning
            for route in routes
            for warning in route["warnings"]
        )
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


def _effective_transit_modes(request: TransitRouteRequest) -> list[str]:
    requested = request.transit_modes
    if requested is None:
        return [TransitMode.TRANSIT.value]
    return [mode.value for mode in requested]


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
    mode_warnings = [
        warning
        for leg in legs
        for warning in leg.pop("_mode_warnings")
    ]
    warnings = _deduplicate_warnings(
        [
            *mode_warnings,
            *(
                warning
                for leg in legs
                for warning in _place_warnings_for_leg(leg)
            ),
        ]
    )
    return {
        "departure_time": _iso_time(itinerary.get("startTime")),
        "arrival_time": _iso_time(itinerary.get("endTime")),
        "duration_seconds": _number(itinerary.get("duration")),
        "transfers": _integer(itinerary.get("transfers")),
        "has_realtime_data": any(leg.get("realtime") is True for leg in legs),
        "has_cancellations": any(_leg_has_cancellations(leg) for leg in legs),
        "warnings": warnings,
        "legs": legs,
    }


def _normalize_leg(leg: dict[str, Any]) -> dict[str, Any]:
    mode, mode_warnings = normalize_provider_mode(leg.get("mode"))
    cancelled = _optional_bool(leg.get("cancelled"))
    if leg.get("tripCancelled") is True:
        cancelled = True
    intermediate_stops = leg.get("intermediateStops")
    if intermediate_stops is None:
        intermediate_stops = []
    if not isinstance(intermediate_stops, list) or not all(
        isinstance(stop, dict) for stop in intermediate_stops
    ):
        raise TransitousInvalidResponseError(
            "Transitous intermediateStops must be an array of objects"
        )
    return {
        "mode": mode,
        "_mode_warnings": mode_warnings,
        "from": _normalize_place(leg.get("from")),
        "to": _normalize_place(leg.get("to")),
        "intermediate_stops": [
            _normalize_place(stop) for stop in intermediate_stops
        ],
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


def normalize_provider_mode(
    value: Any,
) -> tuple[str | None, list[dict[str, Any]]]:
    if not isinstance(value, str):
        return None, []

    normalized = PROVIDER_MODE_NAMES.get(value)
    if normalized is not None:
        return normalized, []

    lowered = value.lower()
    if value in DEBUG_PROVIDER_MODES:
        return lowered, [
            {
                "type": "provider_debug_mode",
                "provider_mode": value,
                "normalized_mode": lowered,
            }
        ]
    return lowered, [
        {
            "type": "unknown_provider_mode",
            "provider_mode": value,
            "normalized_mode": lowered,
        }
    ]


def _normalize_place(value: Any) -> dict[str, Any]:
    place = value if isinstance(value, dict) else {}
    alerts = place.get("alerts")
    if alerts is None:
        alerts = []
    if not isinstance(alerts, list) or not all(
        isinstance(alert, dict) for alert in alerts
    ):
        raise TransitousInvalidResponseError(
            "Transitous place alerts must be an array of objects"
        )
    return {
        "name": _text(place.get("name")),
        "lat": _number(place.get("lat")),
        "lon": _number(place.get("lon")),
        "stop_id": _text(place.get("stopId")),
        "track": _text(place.get("track")),
        "scheduled_track": _text(place.get("scheduledTrack")),
        "cancelled": _optional_bool(place.get("cancelled")),
        "pickup_type": _text(place.get("pickupType")),
        "dropoff_type": _text(place.get("dropoffType")),
        "alerts": [_normalize_alert(alert) for alert in alerts],
    }


def _normalize_alert(alert: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": _text(alert.get("code")),
        "cause": _text(alert.get("cause")),
        "cause_detail": _text(alert.get("causeDetail")),
        "effect": _text(alert.get("effect")),
        "effect_detail": _text(alert.get("effectDetail")),
        "severity": _text(alert.get("severityLevel")),
        "header": _text(alert.get("headerText")),
        "description": _text(alert.get("descriptionText")),
        "url": _text(alert.get("url")),
    }


def _place_warnings_for_leg(leg: dict[str, Any]) -> list[dict[str, Any]]:
    places = [leg["from"], *leg["intermediate_stops"], leg["to"]]
    return [warning for place in places for warning in _place_warnings(place)]


def _place_warnings(place: dict[str, Any]) -> list[dict[str, Any]]:
    context = {
        "stop_id": place["stop_id"],
        "stop_name": place["name"],
    }
    warnings = [
        {"type": "service_alert", **context, **alert}
        for alert in place["alerts"]
    ]
    if (
        place["track"]
        and place["scheduled_track"]
        and place["track"] != place["scheduled_track"]
    ):
        warnings.append(
            {
                "type": "platform_change",
                **context,
                "track": place["track"],
                "scheduled_track": place["scheduled_track"],
            }
        )
    if place["cancelled"] is True:
        warnings.append({"type": "stop_cancelled", **context})
    for field, warning_type in (
        ("pickup_type", "pickup_not_allowed"),
        ("dropoff_type", "dropoff_not_allowed"),
    ):
        if place[field] == "NOT_ALLOWED":
            warnings.append({"type": warning_type, **context})
    return warnings


def _leg_has_cancellations(leg: dict[str, Any]) -> bool:
    if leg["cancelled"] is True:
        return True
    places = [leg["from"], *leg["intermediate_stops"], leg["to"]]
    return any(place["cancelled"] is True for place in places)


def _deduplicate_warnings(
    warnings: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for warning in warnings:
        key = json.dumps(warning, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            seen.add(key)
            result.append(warning)
    return result


def _coordinate_pair(lat: float, lon: float) -> str:
    return f"{lat},{lon}"


def _duration_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


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

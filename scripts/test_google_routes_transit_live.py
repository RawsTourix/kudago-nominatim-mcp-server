from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from time import perf_counter
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_BASE_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
GOOGLE_TRANSIT_FIELD_MASK = ",".join(
    (
        "routes.duration",
        "routes.distanceMeters",
        "routes.routeLabels",
        "routes.legs.duration",
        "routes.legs.distanceMeters",
        "routes.legs.startLocation",
        "routes.legs.endLocation",
        "routes.legs.steps.distanceMeters",
        "routes.legs.steps.staticDuration",
        "routes.legs.steps.travelMode",
        "routes.legs.steps.startLocation",
        "routes.legs.steps.endLocation",
        "routes.legs.steps.transitDetails",
        "routes.localizedValues",
    )
)
REQUIRED_FIELD_MASK_PATHS = {
    "routes.duration",
    "routes.distanceMeters",
    "routes.legs.steps.travelMode",
    "routes.legs.steps.transitDetails",
}
PLANNED_REQUESTS = 12
MAX_HTTP_ATTEMPTS = 16
MAX_RETRIES_PER_REQUEST = 1
REDACTED = "<redacted>"
REDACTED_HEADER = "<redacted-header>"
RAW_RESPONSE_STORAGE_ENABLED = False

CLASSIFICATIONS = {
    "verified_timetable_route",
    "verified_timetable_route_partial_details",
    "structured_transit_route_without_complete_schedule",
    "route_without_transit_details",
    "no_route",
    "provider_error",
    "invalid_response",
}

TECHNICAL_METADATA_KEYS = {
    "case_name",
    "elapsed_ms",
    "http_status",
    "request_attempts",
    "requested_time",
    "response_size_bytes",
    "retry_count",
    "scenario",
    "variant",
}

RAIL_VEHICLE_TYPES = {
    "COMMUTER_TRAIN",
    "HEAVY_RAIL",
    "HIGH_SPEED_TRAIN",
    "LONG_DISTANCE_TRAIN",
    "METRO_RAIL",
    "MONORAIL",
    "RAIL",
    "SUBWAY",
    "TRAIN",
    "TRAM",
}
SUBWAY_VEHICLE_TYPES = {"METRO_RAIL", "SUBWAY"}


@dataclass(frozen=True, slots=True)
class Point:
    label: str
    latitude: float
    longitude: float


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    country: str
    timezone_name: str
    origin: Point
    destination: Point


@dataclass(frozen=True, slots=True)
class RequestCase:
    name: str
    scenario: Scenario
    variant: str
    time_field: str
    requested_time: str
    allowed_travel_modes: tuple[str, ...] = ()
    routing_preference: str | None = None
    repeat_of: str | None = None

    @property
    def preference_semantics(self) -> str:
        if self.allowed_travel_modes or self.routing_preference:
            return "preference_not_strict_filter"
        return "not_requested"


@dataclass(frozen=True, slots=True)
class PreparedRequest:
    url: str
    headers: dict[str, str]
    body: dict[str, Any]


SCENARIOS = (
    Scenario(
        "nakhabino_kurskaya",
        "Russia",
        "Europe/Moscow",
        Point("Nakhabino station", 55.8415879, 37.1849110),
        Point("Kurskaya", 55.7588462, 37.6580446),
    ),
    Scenario(
        "nakhabino_arkhangelskoye",
        "Russia",
        "Europe/Moscow",
        Point("Nakhabino station", 55.8415879, 37.1849110),
        Point("Arkhangelskoye", 55.7885844, 37.2859336),
    ),
    Scenario(
        "berlin_alexanderplatz_hauptbahnhof",
        "Germany",
        "Europe/Berlin",
        Point("Alexanderplatz", 52.5219, 13.4132),
        Point("Berlin Hauptbahnhof", 52.5251, 13.3694),
    ),
    Scenario(
        "new_york_times_square_grand_central",
        "United States",
        "America/New_York",
        Point("Times Square", 40.7580, -73.9855),
        Point("Grand Central Terminal", 40.7527, -73.9772),
    ),
    Scenario(
        "tokyo_station_shinjuku",
        "Japan",
        "Asia/Tokyo",
        Point("Tokyo Station", 35.6812, 139.7671),
        Point("Shinjuku Station", 35.6896, 139.7006),
    ),
    Scenario(
        "nairobi_central_westlands",
        "Kenya",
        "Africa/Nairobi",
        Point("Nairobi Central", -1.286389, 36.817223),
        Point("Westlands", -1.2676, 36.8108),
    ),
    Scenario(
        "harare_centre_avondale",
        "Zimbabwe",
        "Africa/Harare",
        Point("Harare city centre", -17.8252, 31.0335),
        Point("Avondale", -17.7937, 31.0365),
    ),
)


def local_time_to_utc_z(
    local_date: date,
    hour: int,
    timezone_name: str,
) -> str:
    local_value = datetime.combine(
        local_date,
        time(hour=hour),
        tzinfo=ZoneInfo(timezone_name),
    )
    return (
        local_value.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def next_local_date(
    timezone_name: str,
    *,
    local_today: date | None = None,
) -> date:
    today = local_today or datetime.now(ZoneInfo(timezone_name)).date()
    return today + timedelta(days=1)


def build_live_plan(*, local_today: date | None = None) -> list[RequestCase]:
    baseline: list[RequestCase] = []
    for scenario in SCENARIOS:
        departure_time = local_time_to_utc_z(
            next_local_date(scenario.timezone_name, local_today=local_today),
            18,
            scenario.timezone_name,
        )
        baseline.append(
            RequestCase(
                name=f"{scenario.name}__baseline",
                scenario=scenario,
                variant="baseline",
                time_field="departureTime",
                requested_time=departure_time,
            )
        )

    by_scenario = {case.scenario.name: case for case in baseline}
    extra: list[RequestCase] = []
    for scenario_name in (
        "nakhabino_kurskaya",
        "berlin_alexanderplatz_hauptbahnhof",
    ):
        base = by_scenario[scenario_name]
        arrival_time = local_time_to_utc_z(
            next_local_date(
                base.scenario.timezone_name,
                local_today=local_today,
            ),
            19,
            base.scenario.timezone_name,
        )
        extra.append(
            RequestCase(
                name=f"{scenario_name}__arrive_by",
                scenario=base.scenario,
                variant="arrive_by",
                time_field="arrivalTime",
                requested_time=arrival_time,
            )
        )

    moscow = by_scenario["nakhabino_kurskaya"]
    extra.append(
        RequestCase(
            name="nakhabino_kurskaya__fewer_transfers",
            scenario=moscow.scenario,
            variant="preferences",
            time_field=moscow.time_field,
            requested_time=moscow.requested_time,
            allowed_travel_modes=("TRAIN", "SUBWAY", "RAIL"),
            routing_preference="FEWER_TRANSFERS",
        )
    )

    for scenario_name in (
        "nakhabino_kurskaya",
        "berlin_alexanderplatz_hauptbahnhof",
    ):
        base = by_scenario[scenario_name]
        extra.append(
            RequestCase(
                name=f"{scenario_name}__repeat",
                scenario=base.scenario,
                variant="repeat",
                time_field=base.time_field,
                requested_time=base.requested_time,
                repeat_of=base.name,
            )
        )

    plan = [*baseline, *extra]
    if len(plan) != PLANNED_REQUESTS:
        raise AssertionError(
            f"Google Routes live plan must contain {PLANNED_REQUESTS} requests"
        )
    return plan


def build_request_body(case: RequestCase) -> dict[str, Any]:
    body: dict[str, Any] = {
        "origin": {
            "location": {
                "latLng": {
                    "latitude": case.scenario.origin.latitude,
                    "longitude": case.scenario.origin.longitude,
                }
            }
        },
        "destination": {
            "location": {
                "latLng": {
                    "latitude": case.scenario.destination.latitude,
                    "longitude": case.scenario.destination.longitude,
                }
            }
        },
        "travelMode": "TRANSIT",
        case.time_field: case.requested_time,
        "computeAlternativeRoutes": True,
        "languageCode": "en-US",
        "units": "METRIC",
    }
    if case.allowed_travel_modes or case.routing_preference:
        body["transitPreferences"] = {
            "allowedTravelModes": list(case.allowed_travel_modes),
            "routingPreference": case.routing_preference,
        }
    temporal_fields = {"departureTime", "arrivalTime"}.intersection(body)
    if len(temporal_fields) != 1:
        raise ValueError(
            "Transit request must contain exactly one of departureTime or arrivalTime"
        )
    return body


def build_headers(api_key: str, field_mask: str = GOOGLE_TRANSIT_FIELD_MASK) -> dict[str, str]:
    if not api_key:
        raise ValueError("GOOGLE_MAPS_API_KEY is required")
    if not field_mask:
        raise ValueError("X-Goog-FieldMask is required")
    mask_paths = set(field_mask.split(","))
    if not REQUIRED_FIELD_MASK_PATHS.issubset(mask_paths):
        raise ValueError("The Google transit field mask is missing required paths")
    if "routes.*" in mask_paths or any("polyline" in path.casefold() for path in mask_paths):
        raise ValueError("Wildcard routes.* and polyline fields are not allowed")
    return {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": field_mask,
    }


def prepare_request(case: RequestCase, *, base_url: str, api_key: str) -> PreparedRequest:
    if not base_url:
        raise ValueError("GOOGLE_MAPS_BASE_URL is required")
    return PreparedRequest(
        url=base_url.strip(),
        headers=build_headers(api_key),
        body=build_request_body(case),
    )


def sanitize_text(value: str, api_key: str | None) -> str:
    sanitized = value
    if api_key:
        sanitized = sanitized.replace(api_key, REDACTED)
    return re.sub(
        r"(?i)x-goog-api-key",
        REDACTED_HEADER,
        sanitized,
    )


def sanitize_value(value: Any, api_key: str | None) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).casefold() == "x-goog-api-key":
                sanitized[REDACTED_HEADER] = REDACTED
            else:
                sanitized[sanitize_text(str(key), api_key)] = sanitize_value(
                    item,
                    api_key,
                )
        return sanitized
    if isinstance(value, list):
        return [sanitize_value(item, api_key) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_value(item, api_key) for item in value)
    if isinstance(value, str):
        return sanitize_text(value, api_key)
    return value


def sanitize_exception(exc: BaseException, api_key: str | None) -> dict[str, str]:
    return {
        "type": exc.__class__.__name__,
        "message": sanitize_text(str(exc), api_key),
    }


def parse_duration_seconds(value: Any) -> int | float | None:
    if not isinstance(value, str) or not value.endswith("s"):
        return None
    try:
        seconds = float(value[:-1])
    except ValueError:
        return None
    return int(seconds) if seconds.is_integer() else seconds


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def localize_timestamp(value: Any, timezone_name: str) -> str | None:
    parsed = parse_timestamp(value)
    if parsed is None:
        return None
    return parsed.astimezone(ZoneInfo(timezone_name)).isoformat(timespec="seconds")


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _localized_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and isinstance(value.get("text"), str):
        return value["text"]
    return None


def _stop(value: Any) -> dict[str, Any]:
    stop = _dict(value)
    lat_lng = _dict(_dict(stop.get("location")).get("latLng"))
    return {
        "name": stop.get("name") if isinstance(stop.get("name"), str) else None,
        "latitude": lat_lng.get("latitude"),
        "longitude": lat_lng.get("longitude"),
    }


def parse_transit_step(step: dict[str, Any], timezone_name: str) -> dict[str, Any]:
    details = _dict(step.get("transitDetails"))
    stop_details = _dict(details.get("stopDetails"))
    line = _dict(details.get("transitLine"))
    vehicle = _dict(line.get("vehicle"))
    agencies = [
        agency.get("name")
        for agency in _list(line.get("agencies"))
        if isinstance(agency, dict) and isinstance(agency.get("name"), str)
    ]
    departure_time = stop_details.get("departureTime")
    arrival_time = stop_details.get("arrivalTime")
    return {
        "departure_stop": _stop(stop_details.get("departureStop")),
        "arrival_stop": _stop(stop_details.get("arrivalStop")),
        "departure_time": departure_time if isinstance(departure_time, str) else None,
        "arrival_time": arrival_time if isinstance(arrival_time, str) else None,
        "departure_time_local": localize_timestamp(departure_time, timezone_name),
        "arrival_time_local": localize_timestamp(arrival_time, timezone_name),
        "headsign": details.get("headsign") if isinstance(details.get("headsign"), str) else None,
        "stop_count": details.get("stopCount") if isinstance(details.get("stopCount"), int) else None,
        "line_name": line.get("name") if isinstance(line.get("name"), str) else None,
        "line_short_name": line.get("nameShort") if isinstance(line.get("nameShort"), str) else None,
        "vehicle_type": vehicle.get("type") if isinstance(vehicle.get("type"), str) else None,
        "vehicle_name": _localized_text(vehicle.get("name")),
        "agencies": agencies,
    }


def validate_route_times(
    case: RequestCase,
    transit_steps: list[dict[str, Any]],
    duration_seconds: int | float | None,
) -> dict[str, Any]:
    errors: list[str] = []
    chronology_errors: list[str] = []
    parsed_pairs: list[tuple[datetime, datetime]] = []
    for index, step in enumerate(transit_steps):
        departure = parse_timestamp(step.get("departure_time"))
        arrival = parse_timestamp(step.get("arrival_time"))
        if departure is None or arrival is None:
            errors.append(f"transit_step_{index}_missing_or_invalid_timestamp")
            continue
        if arrival < departure:
            chronology_errors.append(
                f"transit_step_{index}_arrival_before_departure"
            )
        parsed_pairs.append((departure, arrival))

    for index in range(1, len(parsed_pairs)):
        previous_arrival = parsed_pairs[index - 1][1]
        departure = parsed_pairs[index][0]
        if departure < previous_arrival:
            chronology_errors.append(
                f"transit_step_{index}_starts_before_previous_arrival"
            )

    errors.extend(chronology_errors)

    requested = parse_timestamp(case.requested_time)
    constraint_valid: bool | None = None
    if requested is None:
        errors.append("invalid_requested_time")
    elif parsed_pairs:
        if case.time_field == "departureTime":
            constraint_valid = parsed_pairs[0][0] >= requested
            if not constraint_valid:
                errors.append("first_transit_departure_before_requested_departure")
        else:
            constraint_valid = parsed_pairs[-1][1] <= requested
            if not constraint_valid:
                errors.append("final_transit_arrival_after_requested_arrival")

    duration_consistent: bool | None = None
    if parsed_pairs and duration_seconds is not None:
        transit_span = (parsed_pairs[-1][1] - parsed_pairs[0][0]).total_seconds()
        duration_consistent = (
            float(duration_seconds) + 300 >= transit_span
            and float(duration_seconds) <= transit_span + 4 * 60 * 60
        )
        if not duration_consistent:
            errors.append("route_duration_inconsistent_with_transit_timestamps")

    all_steps_have_times = bool(transit_steps) and len(parsed_pairs) == len(transit_steps)
    return {
        "timezone": case.scenario.timezone_name,
        "constraint": case.time_field,
        "requested_time": case.requested_time,
        "requested_time_local": localize_timestamp(
            case.requested_time,
            case.scenario.timezone_name,
        ),
        "all_transit_steps_have_times": all_steps_have_times,
        "chronology_valid": all_steps_have_times and not chronology_errors,
        "constraint_valid": constraint_valid,
        "duration_consistent": duration_consistent,
        "valid": (
            all_steps_have_times
            and constraint_valid is True
            and duration_consistent is True
            and not errors
        ),
        "errors": errors,
    }


def classify_normalized_route(route: dict[str, Any]) -> str:
    transit_steps = route.get("transit_steps")
    if not isinstance(transit_steps, list) or not transit_steps:
        return "route_without_transit_details"

    complete_stops = all(
        step["departure_stop"].get("name")
        and step["arrival_stop"].get("name")
        for step in transit_steps
    )
    complete_times = all(
        step.get("departure_time") and step.get("arrival_time")
        for step in transit_steps
    )
    identifiable = all(
        step.get("line_name")
        or step.get("line_short_name")
        or step.get("vehicle_type")
        for step in transit_steps
    )
    time_validation = _dict(route.get("time_validation"))
    schedule_verified = (
        complete_stops
        and complete_times
        and identifiable
        and time_validation.get("valid") is True
    )
    if schedule_verified:
        complete_optional_details = all(
            (step.get("line_name") or step.get("line_short_name"))
            and step.get("headsign")
            and step.get("agencies")
            for step in transit_steps
        )
        if complete_optional_details:
            return "verified_timetable_route"
        return "verified_timetable_route_partial_details"
    if any(
        step["departure_stop"].get("name")
        or step["arrival_stop"].get("name")
        for step in transit_steps
    ):
        return "structured_transit_route_without_complete_schedule"
    return "route_without_transit_details"


def normalize_route(
    route: dict[str, Any],
    route_index: int,
    case: RequestCase,
) -> dict[str, Any]:
    legs = [leg for leg in _list(route.get("legs")) if isinstance(leg, dict)]
    steps = [
        step
        for leg in legs
        for step in _list(leg.get("steps"))
        if isinstance(step, dict)
    ]
    transit_steps = [
        parse_transit_step(step, case.scenario.timezone_name)
        for step in steps
        if isinstance(step.get("transitDetails"), dict)
    ]
    travel_modes = sorted(
        {
            step["travelMode"]
            for step in steps
            if isinstance(step.get("travelMode"), str)
        }
    )
    duration_seconds = parse_duration_seconds(route.get("duration"))
    normalized: dict[str, Any] = {
        "route_index": route_index,
        "distance_meters": route.get("distanceMeters")
        if isinstance(route.get("distanceMeters"), int)
        else None,
        "duration_seconds": duration_seconds,
        "leg_count": len(legs),
        "step_count": len(steps),
        "travel_modes": travel_modes,
        "transit_step_count": len(transit_steps),
        "walking_step_count": sum(mode == "WALK" for mode in (step.get("travelMode") for step in steps)),
        "departure_time": next(
            (
                step["departure_time"]
                for step in transit_steps
                if step.get("departure_time")
            ),
            None,
        ),
        "arrival_time": next(
            (
                step["arrival_time"]
                for step in reversed(transit_steps)
                if step.get("arrival_time")
            ),
            None,
        ),
        "transfer_count": max(len(transit_steps) - 1, 0),
        "fare": _localized_text(
            _dict(route.get("localizedValues")).get("transitFare")
        ),
        "transit_steps": transit_steps,
    }
    normalized["time_validation"] = validate_route_times(
        case,
        transit_steps,
        duration_seconds,
    )
    normalized["classification"] = classify_normalized_route(normalized)
    return normalized


def _provider_error_from_payload(
    payload: Any,
    *,
    status: int | None,
    api_key: str | None,
) -> dict[str, Any]:
    error = _dict(_dict(payload).get("error"))
    return sanitize_value(
        {
            "type": "provider_error",
            "status": status,
            "code": error.get("code"),
            "provider_status": error.get("status"),
            "message": error.get("message")
            if isinstance(error.get("message"), str)
            else "Google Routes returned an error response.",
        },
        api_key,
    )


def parse_response(
    *,
    case: RequestCase,
    http_status: int | None,
    payload: Any,
    elapsed_ms: float = 0.0,
    response_size_bytes: int = 0,
    request_attempts: int = 1,
    provider_error: dict[str, Any] | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "case_name": case.name,
        "scenario": case.scenario.name,
        "country": case.scenario.country,
        "variant": case.variant,
        "time_constraint": case.time_field,
        "requested_time": case.requested_time,
        "preference_semantics": case.preference_semantics,
        "http_status": http_status,
        "elapsed_ms": elapsed_ms,
        "response_size_bytes": response_size_bytes,
        "request_attempts": request_attempts,
        "retry_count": max(request_attempts - 1, 0),
        "route_count": 0,
        "alternative_route_count": 0,
        "classification": None,
        "routes": [],
        "provider_error": None,
    }

    if provider_error is not None:
        result["provider_error"] = sanitize_value(provider_error, api_key)
        result["classification"] = "provider_error"
        return result

    payload_error = isinstance(payload, dict) and payload.get("error") is not None
    if http_status is None or not 200 <= http_status < 300 or payload_error:
        result["provider_error"] = _provider_error_from_payload(
            payload,
            status=http_status,
            api_key=api_key,
        )
        result["classification"] = "provider_error"
        return result

    if not isinstance(payload, dict):
        result["classification"] = "invalid_response"
        return result
    if "routes" not in payload:
        result["classification"] = "no_route"
        return result
    routes = payload.get("routes")
    if not isinstance(routes, list):
        result["classification"] = "invalid_response"
        return result
    if not routes:
        result["classification"] = "no_route"
        return result
    if any(not isinstance(route, dict) for route in routes):
        result["classification"] = "invalid_response"
        return result

    normalized_routes = [
        normalize_route(route, index, case)
        for index, route in enumerate(routes)
    ]
    priority = (
        "verified_timetable_route",
        "verified_timetable_route_partial_details",
        "structured_transit_route_without_complete_schedule",
        "route_without_transit_details",
    )
    result.update(
        {
            "route_count": len(normalized_routes),
            "alternative_route_count": max(len(normalized_routes) - 1, 0),
            "classification": next(
                classification
                for classification in priority
                if any(
                    route["classification"] == classification
                    for route in normalized_routes
                )
            ),
            "routes": normalized_routes,
        }
    )
    if result["classification"] not in CLASSIFICATIONS:
        raise AssertionError("Unexpected Google transit classification")
    return result


def normalize_for_repeat_comparison(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: normalize_for_repeat_comparison(item)
            for key, item in value.items()
            if key not in TECHNICAL_METADATA_KEYS
        }
    if isinstance(value, list):
        return [normalize_for_repeat_comparison(item) for item in value]
    return value


def repeat_digest(value: Any) -> str:
    normalized = normalize_for_repeat_comparison(value)
    encoded = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def compare_repeat_results(first: dict[str, Any], second: dict[str, Any]) -> bool:
    return repeat_digest(first) == repeat_digest(second)


def _best_route(result: dict[str, Any]) -> dict[str, Any] | None:
    routes = result.get("routes")
    if not isinstance(routes, list) or not routes:
        return None
    return routes[0] if isinstance(routes[0], dict) else None


def _transit_vehicle_types(result: dict[str, Any]) -> list[str]:
    return sorted(
        {
            step["vehicle_type"]
            for route in _list(result.get("routes"))
            if isinstance(route, dict)
            for step in _list(route.get("transit_steps"))
            if isinstance(step, dict) and isinstance(step.get("vehicle_type"), str)
        }
    )


def analyze_moscow(result: dict[str, Any]) -> dict[str, Any]:
    steps = [
        step
        for route in _list(result.get("routes"))
        if isinstance(route, dict)
        for step in _list(route.get("transit_steps"))
        if isinstance(step, dict)
    ]
    departure_stop_names = sorted(
        {
            stop["name"]
            for step in steps
            for stop in (step.get("departure_stop"),)
            if isinstance(stop, dict) and isinstance(stop.get("name"), str)
        }
    )
    arrival_stop_names = sorted(
        {
            stop["name"]
            for step in steps
            for stop in (step.get("arrival_stop"),)
            if isinstance(stop, dict) and isinstance(stop.get("name"), str)
        }
    )
    stop_names = sorted({*departure_stop_names, *arrival_stop_names})
    line_names = sorted(
        {
            name
            for step in steps
            for name in (step.get("line_name"), step.get("line_short_name"))
            if isinstance(name, str) and name
        }
    )
    vehicle_types = sorted(
        {
            step["vehicle_type"]
            for step in steps
            if isinstance(step.get("vehicle_type"), str)
        }
    )
    headsigns = sorted(
        {
            step["headsign"]
            for step in steps
            if isinstance(step.get("headsign"), str)
        }
    )
    agencies = sorted(
        {
            agency
            for step in steps
            for agency in _list(step.get("agencies"))
            if isinstance(agency, str)
        }
    )
    searchable_stops = " ".join(stop_names).casefold()
    searchable_lines = " ".join(line_names).casefold()
    nakhabino_found = any(
        marker in searchable_stops for marker in ("nakhabino", "нахабино")
    )
    kurskaya_found = any(
        marker in searchable_stops for marker in ("kursk", "курск")
    )
    literal_mcd_marker = any(
        marker in searchable_lines
        for marker in ("mcd", "мцд", "d2", "d-2", "д2", "д-2")
    )
    rail_present = bool(set(vehicle_types).intersection(RAIL_VEHICLE_TYPES))
    subway_present = bool(set(vehicle_types).intersection(SUBWAY_VEHICLE_TYPES))
    exact_times = bool(steps) and all(
        step.get("departure_time") and step.get("arrival_time") for step in steps
    )
    sequence_reconstructible = bool(steps) and all(
        _dict(step.get("departure_stop")).get("name")
        and _dict(step.get("arrival_stop")).get("name")
        and step.get("departure_time")
        and step.get("arrival_time")
        for step in steps
    )
    return {
        "departure_stop_names": departure_stop_names,
        "arrival_stop_names": arrival_stop_names,
        "line_names": line_names,
        "line_short_names": sorted(
            {
                step["line_short_name"]
                for step in steps
                if isinstance(step.get("line_short_name"), str)
            }
        ),
        "vehicle_types": vehicle_types,
        "headsigns": headsigns,
        "agencies": agencies,
        "nakhabino_found": nakhabino_found,
        "kurskaya_found": kurskaya_found,
        "rail_segment_present": rail_present,
        "subway_segment_present": subway_present,
        "literal_mcd_or_d2_marker": literal_mcd_marker,
        "exact_times_present": exact_times,
        "transfer_sequence_reconstructible": sequence_reconstructible,
        "structurally_consistent_with_mcd2": (
            nakhabino_found
            and kurskaya_found
            and rail_present
            and exact_times
            and sequence_reconstructible
        ),
        "alternative_routes_present": int(result.get("alternative_route_count") or 0) > 0,
    }


def compare_preferences(
    baseline: dict[str, Any],
    preferred: dict[str, Any],
) -> dict[str, Any]:
    baseline_route = _best_route(baseline)
    preferred_route = _best_route(preferred)
    allowed = {"TRAIN", "SUBWAY", "RAIL"}
    actual_modes = set(_transit_vehicle_types(preferred))
    covered_by_rail_preference = (
        actual_modes.intersection(RAIL_VEHICLE_TYPES)
        if "RAIL" in allowed
        else set()
    )
    return {
        "semantics": "preference_not_strict_filter",
        "baseline_transfer_count": baseline_route.get("transfer_count")
        if baseline_route
        else None,
        "preferred_transfer_count": preferred_route.get("transfer_count")
        if preferred_route
        else None,
        "baseline_duration_seconds": baseline_route.get("duration_seconds")
        if baseline_route
        else None,
        "preferred_duration_seconds": preferred_route.get("duration_seconds")
        if preferred_route
        else None,
        "actual_transit_vehicle_types": sorted(actual_modes),
        "other_transit_vehicle_types": sorted(
            actual_modes - allowed - covered_by_rail_preference
        ),
    }


def choose_recommendation(results: list[dict[str, Any]]) -> str:
    baseline = [result for result in results if result.get("variant") == "baseline"]
    verified = {
        "verified_timetable_route",
        "verified_timetable_route_partial_details",
    }
    verified_count = sum(result.get("classification") in verified for result in baseline)
    moscow = next(
        (
            result
            for result in baseline
            if result.get("scenario") == "nakhabino_kurskaya"
        ),
        None,
    )
    provider_errors = sum(
        result.get("classification") == "provider_error" for result in baseline
    )
    if not baseline or provider_errors == len(baseline):
        return "inconclusive"
    if verified_count >= 6 and moscow and moscow.get("classification") in verified:
        return "recommended_as_primary_with_transitous_fallback"
    if verified_count >= 2:
        return "recommended_only_as_regional_provider"
    if verified_count == 0 and provider_errors == 0:
        return "not_recommended"
    return "inconclusive"


def build_report(
    results: list[dict[str, Any]],
    *,
    http_attempt_count: int,
) -> dict[str, Any]:
    by_name = {result["case_name"]: result for result in results}
    moscow_base = by_name["nakhabino_kurskaya__baseline"]
    berlin_base = by_name["berlin_alexanderplatz_hauptbahnhof__baseline"]
    preferences = by_name["nakhabino_kurskaya__fewer_transfers"]
    repeat_comparisons = {
        "nakhabino_kurskaya": compare_repeat_results(
            moscow_base,
            by_name["nakhabino_kurskaya__repeat"],
        ),
        "berlin_alexanderplatz_hauptbahnhof": compare_repeat_results(
            berlin_base,
            by_name["berlin_alexanderplatz_hauptbahnhof__repeat"],
        ),
    }
    preference_comparison = compare_preferences(moscow_base, preferences)
    moscow = analyze_moscow(moscow_base)
    baseline = [result for result in results if result["variant"] == "baseline"]
    covered_classes = {
        "verified_timetable_route",
        "verified_timetable_route_partial_details",
        "structured_transit_route_without_complete_schedule",
    }
    covered_countries = sorted(
        {
            result["country"]
            for result in baseline
            if result["classification"] in covered_classes
        }
    )
    no_route = [
        result["case_name"]
        for result in results
        if result["classification"] == "no_route"
    ]
    provider_errors = [
        result["case_name"]
        for result in results
        if result["classification"] == "provider_error"
    ]
    fare_cases = [
        result["case_name"]
        for result in results
        if any(route.get("fare") for route in _list(result.get("routes")))
    ]
    arrive_by = {
        result["scenario"]: {
            "classification": result["classification"],
            "constraint_valid": all(
                _dict(route.get("time_validation")).get("constraint_valid") is True
                for route in _list(result.get("routes"))
            )
            if result.get("route_count")
            else None,
        }
        for result in results
        if result["variant"] == "arrive_by"
    }
    alternatives = {
        result["case_name"]: result["alternative_route_count"]
        for result in results
    }
    recommendation = choose_recommendation(results)
    questions = {
        "1_nakhabino_to_kurskaya": moscow_base["classification"],
        "2_nakhabino_station_recognized": moscow["nakhabino_found"],
        "3_kurskaya_recognized": moscow["kurskaya_found"],
        "4_mcd2_or_equivalent_rail_segment": moscow["structurally_consistent_with_mcd2"],
        "5_exact_departure_arrival_times": moscow["exact_times_present"],
        "6_nakhabino_to_arkhangelskoye": by_name[
            "nakhabino_arkhangelskoye__baseline"
        ]["classification"],
        "7_covered_countries": covered_countries,
        "8_no_route": no_route,
        "9_provider_errors": provider_errors,
        "10_arrive_by": arrive_by,
        "11_alternative_routes": alternatives,
        "12_fewer_transfers_change": preference_comparison,
        "13_preferences_returned_other_modes": preference_comparison[
            "other_transit_vehicle_types"
        ],
        "14_fare": fare_cases,
        "15_repeats_equal": repeat_comparisons,
        "16_cloud_sku_and_usage": {
            "actual_sku": None,
            "request_attempts_observed_locally": http_attempt_count,
            "status": "requires_authenticated_google_cloud_metrics_or_billing",
        },
        "17_primary_provider": recommendation,
        "18_transitous_fallback": recommendation
        == "recommended_as_primary_with_transitous_fallback",
        "19_geoapify_approximated_fallback": (
            "not_for_timetable_routing; only consider as explicitly approximate network fallback"
        ),
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "planned_request_count": len(results),
        "http_attempt_count": http_attempt_count,
        "http_attempt_limit": MAX_HTTP_ATTEMPTS,
        "field_mask": GOOGLE_TRANSIT_FIELD_MASK,
        "raw_response_storage_enabled": RAW_RESPONSE_STORAGE_ENABLED,
        "results": results,
        "repeat_comparisons": repeat_comparisons,
        "preference_comparison": preference_comparison,
        "moscow_mcd2_evidence": moscow,
        "billing": {
            "documented_candidate_sku": "Routes: Compute Routes Essentials",
            "actual_sku": None,
            "actual_sku_status": "not_exposed_by_compute_routes_response",
        },
        "questions": questions,
        "recommendation": recommendation,
    }


class LiveRunner:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        base_url: str,
        api_key: str,
        retry_delay_seconds: float,
    ) -> None:
        self.client = client
        self.base_url = base_url
        self.api_key = api_key
        self.retry_delay_seconds = retry_delay_seconds
        self.http_attempt_count = 0

    async def execute(self, case: RequestCase) -> dict[str, Any]:
        prepared = prepare_request(
            case,
            base_url=self.base_url,
            api_key=self.api_key,
        )
        started = perf_counter()
        status: int | None = None
        payload: Any = None
        response_size = 0
        provider_error: dict[str, Any] | None = None
        request_attempts = 0

        while True:
            if self.http_attempt_count >= MAX_HTTP_ATTEMPTS:
                provider_error = {
                    "type": "request_budget_exhausted",
                    "message": "The live diagnostic HTTP attempt budget was exhausted.",
                }
                break
            self.http_attempt_count += 1
            request_attempts += 1
            retryable = False
            try:
                response = await self.client.post(
                    prepared.url,
                    headers=prepared.headers,
                    json=prepared.body,
                )
                status = response.status_code
                response_size = len(response.content)
                try:
                    payload = response.json()
                except ValueError:
                    payload = None
                retryable = 500 <= status < 600
            except httpx.TimeoutException as exc:
                provider_error = sanitize_exception(exc, self.api_key)
                retryable = True
            except httpx.RequestError as exc:
                provider_error = sanitize_exception(exc, self.api_key)

            can_retry = (
                retryable
                and request_attempts <= MAX_RETRIES_PER_REQUEST
                and self.http_attempt_count < MAX_HTTP_ATTEMPTS
            )
            if not can_retry:
                break
            await asyncio.sleep(self.retry_delay_seconds)
            provider_error = None

        elapsed_ms = round((perf_counter() - started) * 1000, 1)
        return parse_response(
            case=case,
            http_status=status,
            payload=payload,
            elapsed_ms=elapsed_ms,
            response_size_bytes=response_size,
            request_attempts=request_attempts,
            provider_error=provider_error,
            api_key=self.api_key,
        )


def load_live_config() -> tuple[str, str]:
    load_dotenv(ROOT / ".env", override=False)
    base_url = os.getenv("GOOGLE_MAPS_BASE_URL", "").strip()
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
    missing = [
        name
        for name, value in (
            ("GOOGLE_MAPS_BASE_URL", base_url),
            ("GOOGLE_MAPS_API_KEY", api_key),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing required variables: {', '.join(missing)}")
    return base_url, api_key


async def run_diagnostics(
    *,
    base_url: str,
    api_key: str,
    local_today: date | None = None,
    timeout_seconds: float = 20.0,
    retry_delay_seconds: float = 0.25,
) -> dict[str, Any]:
    plan = build_live_plan(local_today=local_today)
    async with httpx.AsyncClient(
        timeout=timeout_seconds,
        follow_redirects=False,
        trust_env=True,
    ) as client:
        runner = LiveRunner(
            client=client,
            base_url=base_url,
            api_key=api_key,
            retry_delay_seconds=retry_delay_seconds,
        )
        results = [await runner.execute(case) for case in plan]
    return build_report(results, http_attempt_count=runner.http_attempt_count)


def print_report(report: dict[str, Any]) -> None:
    print("scenario | HTTP | routes | class | transit steps | stops | lines | times | fare")
    for result in report["results"]:
        routes = _list(result.get("routes"))
        transit_steps = [
            step
            for route in routes
            if isinstance(route, dict)
            for step in _list(route.get("transit_steps"))
            if isinstance(step, dict)
        ]
        stop_count = sum(
            bool(_dict(step.get("departure_stop")).get("name"))
            + bool(_dict(step.get("arrival_stop")).get("name"))
            for step in transit_steps
        )
        line_count = sum(
            bool(step.get("line_name") or step.get("line_short_name"))
            for step in transit_steps
        )
        time_count = sum(
            bool(step.get("departure_time") and step.get("arrival_time"))
            for step in transit_steps
        )
        fare_count = sum(bool(route.get("fare")) for route in routes)
        print(
            f"{result['case_name']} | {result['http_status']} | "
            f"{result['route_count']} | {result['classification']} | "
            f"{len(transit_steps)} | {stop_count} | {line_count} | "
            f"{time_count} | {fare_count}"
        )
    print(
        json.dumps(
            {
                "moscow_mcd2_evidence": report["moscow_mcd2_evidence"],
                "preference_comparison": report["preference_comparison"],
                "repeat_comparisons": report["repeat_comparisons"],
                "billing": report["billing"],
                "questions": report["questions"],
                "recommendation": report["recommendation"],
                "request_budget": {
                    "planned": report["planned_request_count"],
                    "http_attempts": report["http_attempt_count"],
                    "limit": report["http_attempt_limit"],
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safely diagnose Google Routes API transit coverage.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--retry-delay-seconds", type=float, default=0.25)
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    if args.timeout_seconds <= 0:
        raise ValueError("--timeout-seconds must be positive")
    if args.retry_delay_seconds < 0:
        raise ValueError("--retry-delay-seconds must be non-negative")
    base_url, api_key = load_live_config()
    report = await run_diagnostics(
        base_url=base_url,
        api_key=api_key,
        timeout_seconds=args.timeout_seconds,
        retry_delay_seconds=args.retry_delay_seconds,
    )
    print_report(report)


if __name__ == "__main__":
    asyncio.run(main())

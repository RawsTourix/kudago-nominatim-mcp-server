from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import quote_plus

import httpx
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")


DEFAULT_BASE_URL = "https://api.geoapify.com/v1/routing"
ROUTING_MODES = ("transit", "approximated_transit")
MIN_REQUEST_DELAY_SECONDS = 0.25
MAX_REQUESTS = 18
RAW_DIRECTORY = ROOT / ".tmp" / "geoapify-live"
REDACTED = "<redacted>"

DOCUMENTED_REQUEST_PARAMETERS = {
    "apiKey",
    "waypoints",
    "mode",
    "intermediate_waypoint_mode",
    "type",
    "units",
    "lang",
    "avoid",
    "details",
    "traffic",
    "max_speed",
    "format",
}
UNSUPPORTED_TEMPORAL_PARAMETERS = {
    "departure_time",
    "arrival_time",
    "date",
    "time",
}

TRANSIT_INSTRUCTION_TYPES = {
    "Transit",
    "TransitTransfer",
    "TransitRemainOn",
    "TransitConnectionStart",
    "TransitConnectionTransfer",
    "TransitConnectionDestination",
    "PostTransitConnectionDestination",
}
OBSERVED_FIELD_NAMES = {
    "departure",
    "departure_time",
    "arrival",
    "arrival_time",
    "timestamp",
    "service_date",
    "schedule",
    "realtime",
    "delay",
    "stop_id",
    "stop_name",
    "route_name",
    "route_short_name",
    "line",
    "agency",
}
DEPARTURE_FIELD_NAMES = {"departure", "departure_time"}
ARRIVAL_FIELD_NAMES = {"arrival", "arrival_time"}
SERVICE_DATE_FIELD_NAMES = {"service_date", "schedule"}
REALTIME_FIELD_NAMES = {"realtime", "delay"}
LINE_FIELD_NAMES = {"line", "route_name", "route_short_name"}
STOP_FIELD_NAMES = {"stop_name"}
MODE_FIELD_NAMES = {"mode", "travel_mode", "transport_mode"}
COMPARISON_OMIT_KEYS = {
    "apikey",
    "geometry",
    "metadata",
    "request_id",
    "requestid",
    "trace_id",
    "traceid",
}


@dataclass(frozen=True, slots=True)
class Point:
    label: str
    latitude: float
    longitude: float


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    city: str
    origin: Point
    destination: Point


SCENARIOS = (
    Scenario(
        "nakhabino_kurskaya",
        "Moscow",
        Point("Nakhabino station", 55.8415879, 37.1849110),
        Point("Kurskaya metro", 55.7588462, 37.6580446),
    ),
    Scenario(
        "nakhabino_arkhangelskoye",
        "Moscow region",
        Point("Nakhabino station", 55.8415879, 37.1849110),
        Point("Arkhangelskoye museum", 55.7885844, 37.2859336),
    ),
    Scenario(
        "berlin_alexanderplatz_hauptbahnhof",
        "Berlin",
        Point("Alexanderplatz", 52.5219, 13.4132),
        Point("Berlin Hauptbahnhof", 52.5251, 13.3694),
    ),
    Scenario(
        "new_york_times_square_grand_central",
        "New York",
        Point("Times Square", 40.7580, -73.9855),
        Point("Grand Central Terminal", 40.7527, -73.9772),
    ),
    Scenario(
        "tokyo_station_shinjuku",
        "Tokyo",
        Point("Tokyo Station", 35.6812, 139.7671),
        Point("Shinjuku Station", 35.6896, 139.7006),
    ),
    Scenario(
        "nairobi_central_westlands",
        "Nairobi",
        Point("Nairobi Central", -1.286389, 36.817223),
        Point("Westlands", -1.2676, 36.8108),
    ),
    Scenario(
        "harare_centre_avondale",
        "Harare",
        Point("Harare city centre", -17.8252, 31.0335),
        Point("Avondale", -17.7937, 31.0365),
    ),
)

REPEAT_SCENARIOS = {
    "nakhabino_kurskaya",
    "berlin_alexanderplatz_hauptbahnhof",
}


def normalize_base_url(value: str) -> str:
    return value.rstrip("/")


def format_waypoints(origin: Point, destination: Point) -> str:
    return (
        f"{origin.latitude},{origin.longitude}|"
        f"{destination.latitude},{destination.longitude}"
    )


def build_request_params(
    scenario: Scenario,
    mode: str,
    api_key: str,
) -> dict[str, str]:
    if mode not in ROUTING_MODES:
        raise ValueError(f"Unsupported Geoapify routing mode: {mode}")
    return {
        "waypoints": format_waypoints(scenario.origin, scenario.destination),
        "mode": mode,
        "format": "json",
        "lang": "en",
        "details": "instruction_details",
        "apiKey": api_key,
    }


def build_main_matrix(api_key: str) -> list[tuple[Scenario, str, dict[str, str]]]:
    matrix = [
        (scenario, mode, build_request_params(scenario, mode, api_key))
        for scenario in SCENARIOS
        for mode in ROUTING_MODES
    ]
    if len(matrix) != 14:
        raise AssertionError("Geoapify main matrix must contain exactly 14 requests")
    return matrix


def sanitize_text(value: str, api_key: str | None) -> str:
    sanitized = value
    if api_key:
        sanitized = sanitized.replace(api_key, REDACTED)
        sanitized = sanitized.replace(quote_plus(api_key), REDACTED)
    return re.sub(
        r"(?i)(apikey\s*=\s*)[^&\s]+",
        rf"\g<1>{REDACTED}",
        sanitized,
    )


def sanitize_value(value: Any, api_key: str | None) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                REDACTED
                if key.casefold() == "apikey"
                else sanitize_value(item, api_key)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_value(item, api_key) for item in value]
    if isinstance(value, str):
        return sanitize_text(value, api_key)
    return value


def request_summary(params: dict[str, str]) -> dict[str, str]:
    return {
        key: REDACTED if key.casefold() == "apikey" else value
        for key, value in params.items()
    }


def coordinate_count(value: Any) -> int:
    if isinstance(value, list):
        if len(value) >= 2 and all(
            isinstance(item, (int, float)) for item in value[:2]
        ):
            return 1
        return sum(coordinate_count(item) for item in value)
    if isinstance(value, dict):
        return sum(coordinate_count(item) for item in value.values())
    return 0


def geometry_summary(value: Any) -> dict[str, Any]:
    geometry_type = value.get("type") if isinstance(value, dict) else None
    return {
        "redacted": True,
        "type": geometry_type or type(value).__name__,
        "coordinate_count": coordinate_count(value),
    }


def compact_raw_payload(value: Any, api_key: str | None) -> Any:
    sanitized = sanitize_value(value, api_key)
    if isinstance(sanitized, dict):
        return {
            key: (
                geometry_summary(item)
                if key.casefold() == "geometry"
                else compact_raw_payload(item, None)
            )
            for key, item in sanitized.items()
        }
    if isinstance(sanitized, list):
        return [compact_raw_payload(item, None) for item in sanitized]
    return sanitized


def walk_fields(value: Any) -> list[tuple[str, Any]]:
    fields: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = key.casefold()
            if normalized_key in OBSERVED_FIELD_NAMES:
                fields.append((normalized_key, item))
            fields.extend(walk_fields(item))
    elif isinstance(value, list):
        for item in value:
            fields.extend(walk_fields(item))
    return fields


def has_non_empty_field(
    fields: list[tuple[str, Any]],
    names: set[str],
) -> bool:
    return any(name in names and value is not None for name, value in fields)


def compact_field_evidence(fields: list[tuple[str, Any]]) -> dict[str, Any]:
    evidence: dict[str, dict[str, Any]] = {}
    for name, value in fields:
        current = evidence.setdefault(name, {"count": 0, "samples": []})
        current["count"] += 1
        sample = value if isinstance(value, (str, int, float, bool)) else type(value).__name__
        if sample not in current["samples"] and len(current["samples"]) < 5:
            current["samples"].append(sample)
    return evidence


def flatten_steps(route: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    legs = route.get("legs")
    if not isinstance(legs, list):
        return [], 0
    steps: list[dict[str, Any]] = []
    for leg in legs:
        if not isinstance(leg, dict) or not isinstance(leg.get("steps"), list):
            continue
        steps.extend(step for step in leg["steps"] if isinstance(step, dict))
    return steps, len(legs)


def collect_scalar_values(value: Any, target_keys: set[str]) -> list[str]:
    result: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key.casefold() in target_keys:
                if isinstance(item, (str, int, float)):
                    result.append(str(item))
                elif isinstance(item, dict):
                    for detail_key in ("name", "short_name", "ref", "id"):
                        detail = item.get(detail_key)
                        if isinstance(detail, (str, int, float)):
                            result.append(str(detail))
            result.extend(collect_scalar_values(item, target_keys))
    elif isinstance(value, list):
        for item in value:
            result.extend(collect_scalar_values(item, target_keys))
    return sorted(set(result))


def collect_step_modes(steps: list[dict[str, Any]]) -> list[str]:
    modes: list[str] = []
    for step in steps:
        modes.extend(collect_scalar_values(step, MODE_FIELD_NAMES))
    return sorted(set(modes))


def collect_transit_instruction_types(steps: list[dict[str, Any]]) -> list[str]:
    result: set[str] = set()
    for step in steps:
        instruction = step.get("instruction")
        if not isinstance(instruction, dict):
            continue
        instruction_type = instruction.get("type")
        if instruction_type in TRANSIT_INSTRUCTION_TYPES:
            result.add(instruction_type)
    return sorted(result)


def has_geometry(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            (key.casefold() == "geometry" and item is not None)
            or has_geometry(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(has_geometry(item) for item in value)
    return False


def classify_route(summary: dict[str, Any], mode: str) -> str:
    if summary.get("provider_error") is not None:
        return "provider_error"
    if summary.get("invalid_response"):
        return "invalid_response"
    if not summary.get("result_count"):
        return "no_route"
    if mode == "approximated_transit":
        return "approximated_network_route"

    has_identifiable_transit = bool(
        summary.get("transit_instruction_types")
        or summary.get("named_lines")
        or summary.get("named_stops")
        or any(
            item.casefold() not in {"walk", "walking"}
            for item in summary.get("step_modes", [])
        )
    )
    if (
        summary.get("has_departure_timestamps")
        and summary.get("has_arrival_timestamps")
        and summary.get("has_service_dates")
        and summary.get("named_lines")
    ):
        return "verified_timetable_route"
    if has_identifiable_transit:
        return "structured_transit_route_without_schedule"
    return "generic_route_only"


def parse_response(
    *,
    scenario: str,
    mode: str,
    http_status: int | None,
    elapsed_ms: float,
    response_size_bytes: int,
    payload: Any,
    request: dict[str, str],
    provider_error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "scenario": scenario,
        "mode": mode,
        "request": request,
        "http_status": http_status,
        "elapsed_ms": elapsed_ms,
        "response_size_bytes": response_size_bytes,
        "result_count": 0,
        "classification": None,
        "distance_meters": None,
        "duration_seconds": None,
        "leg_count": 0,
        "step_count": 0,
        "step_modes": [],
        "transit_instruction_types": [],
        "named_lines": [],
        "named_stops": [],
        "has_departure_timestamps": False,
        "has_arrival_timestamps": False,
        "has_service_dates": False,
        "has_realtime_flags": False,
        "has_route_geometry": False,
        "observed_fields": {},
        "mcd2_recognized": False,
        "provider_error": provider_error,
        "invalid_response": False,
    }

    if provider_error is not None or http_status is None or not 200 <= http_status < 300:
        if summary["provider_error"] is None:
            summary["provider_error"] = {
                "type": "http_error",
                "status": http_status,
            }
        summary["classification"] = "provider_error"
        return summary

    if isinstance(payload, dict) and (
        payload.get("error") is not None or payload.get("statusCode") not in (None, 200)
    ):
        summary["provider_error"] = {
            "type": "provider_error",
            "error": payload.get("error"),
            "message": payload.get("message"),
            "status_code": payload.get("statusCode"),
        }
        summary["classification"] = "provider_error"
        return summary

    if not (
        isinstance(payload, dict)
        and isinstance(payload.get("properties"), dict)
        and isinstance(payload.get("results"), list)
    ):
        summary["invalid_response"] = True
        summary["classification"] = "invalid_response"
        return summary

    results = payload["results"]
    summary["result_count"] = len(results)
    if not results:
        summary["classification"] = "no_route"
        return summary
    route = results[0]
    if not isinstance(route, dict) or not isinstance(route.get("legs"), list):
        summary["invalid_response"] = True
        summary["classification"] = "invalid_response"
        return summary

    steps, leg_count = flatten_steps(route)
    fields = walk_fields(payload)
    summary.update(
        {
            "distance_meters": route.get("distance"),
            "duration_seconds": route.get("time"),
            "leg_count": leg_count,
            "step_count": len(steps),
            "step_modes": collect_step_modes(steps),
            "transit_instruction_types": collect_transit_instruction_types(steps),
            "named_lines": collect_scalar_values(route, LINE_FIELD_NAMES),
            "named_stops": collect_scalar_values(route, STOP_FIELD_NAMES),
            "has_departure_timestamps": has_non_empty_field(
                fields,
                DEPARTURE_FIELD_NAMES,
            ),
            "has_arrival_timestamps": has_non_empty_field(
                fields,
                ARRIVAL_FIELD_NAMES,
            ),
            "has_service_dates": has_non_empty_field(
                fields,
                SERVICE_DATE_FIELD_NAMES,
            ),
            "has_realtime_flags": has_non_empty_field(
                fields,
                REALTIME_FIELD_NAMES,
            ),
            "has_route_geometry": has_geometry(route),
            "observed_fields": compact_field_evidence(fields),
        }
    )
    searchable = " ".join(summary["named_lines"]).casefold()
    summary["mcd2_recognized"] = any(
        marker in searchable for marker in ("мцд-2", "mcd-2", "mcd 2", "d2")
    )
    summary["classification"] = classify_route(summary, mode)
    return summary


def normalize_for_repeat_comparison(payload: Any) -> Any:
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        payload = payload["results"]
    if isinstance(payload, dict):
        return {
            key: normalize_for_repeat_comparison(item)
            for key, item in payload.items()
            if key.casefold() not in COMPARISON_OMIT_KEYS
        }
    if isinstance(payload, list):
        return [normalize_for_repeat_comparison(item) for item in payload]
    return payload


def repeat_digest(payload: Any) -> str:
    normalized = normalize_for_repeat_comparison(payload)
    encoded = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def compare_repeat_payloads(first: Any, second: Any) -> bool:
    return repeat_digest(first) == repeat_digest(second)


def trust_flags(summary: dict[str, Any]) -> dict[str, Any]:
    classification = summary["classification"]
    approximated = summary["mode"] == "approximated_transit"
    return {
        "route_available": classification
        not in {"no_route", "provider_error", "invalid_response"},
        "route_verified": classification
        in {"verified_timetable_route", "structured_transit_route_without_schedule"},
        "schedule_verified": classification == "verified_timetable_route",
        "realtime_data_present": bool(summary["has_realtime_flags"]),
        "approximate": approximated,
        "provider_mode": summary["mode"],
    }


class LiveRunner:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        base_url: str,
        api_key: str,
        delay_seconds: float,
        raw_directory: Path,
    ) -> None:
        self.client = client
        self.base_url = base_url
        self.api_key = api_key
        self.delay_seconds = delay_seconds
        self.raw_directory = raw_directory
        self.request_count = 0

    async def execute(
        self,
        scenario: Scenario,
        mode: str,
        *,
        suffix: str = "main",
    ) -> tuple[dict[str, Any], Any]:
        if self.request_count >= MAX_REQUESTS:
            raise RuntimeError(f"Geoapify request limit exceeded: {MAX_REQUESTS}")
        if self.request_count:
            await asyncio.sleep(self.delay_seconds)
        self.request_count += 1

        params = build_request_params(scenario, mode, self.api_key)
        safe_request = request_summary(params)
        started = perf_counter()
        payload: Any = None
        status: int | None = None
        response_size = 0
        provider_error: dict[str, Any] | None = None
        try:
            response = await self.client.get(self.base_url, params=params)
            status = response.status_code
            response_size = len(response.content)
            try:
                payload = response.json()
            except ValueError:
                payload = None
                if not response.is_success:
                    provider_error = {
                        "type": "http_error",
                        "status": status,
                        "message": "Geoapify returned a non-JSON error response.",
                    }
        except httpx.HTTPError as exc:
            provider_error = {
                "type": exc.__class__.__name__,
                "message": sanitize_text(str(exc), self.api_key),
            }

        elapsed_ms = round((perf_counter() - started) * 1000, 1)
        sanitized_payload = sanitize_value(payload, self.api_key)
        if provider_error is None and status is not None and not 200 <= status < 300:
            error_payload = sanitized_payload if isinstance(sanitized_payload, dict) else {}
            provider_error = {
                "type": "http_error",
                "status": status,
                "error": error_payload.get("error"),
                "message": error_payload.get("message"),
            }
        summary = parse_response(
            scenario=scenario.name,
            mode=mode,
            http_status=status,
            elapsed_ms=elapsed_ms,
            response_size_bytes=response_size,
            payload=sanitized_payload,
            request=safe_request,
            provider_error=provider_error,
        )
        summary["trust_flags"] = trust_flags(summary)
        raw_record = {
            "scenario": scenario.name,
            "mode": mode,
            "request": safe_request,
            "http_status": status,
            "payload": compact_raw_payload(sanitized_payload, None),
            "provider_error": provider_error,
        }
        raw_path = self.raw_directory / (
            f"{self.request_count:02d}-{scenario.name}-{mode}-{suffix}.json"
        )
        raw_path.write_text(
            json.dumps(raw_record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return summary, sanitized_payload


def compare_modes(main_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    comparisons: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        by_mode = {
            result["mode"]: result
            for result in main_results
            if result["scenario"] == scenario.name
        }
        transit = by_mode["transit"]
        approximated = by_mode["approximated_transit"]
        duration_a = transit.get("duration_seconds")
        duration_b = approximated.get("duration_seconds")
        distance_a = transit.get("distance_meters")
        distance_b = approximated.get("distance_meters")
        comparisons.append(
            {
                "scenario": scenario.name,
                "city": scenario.city,
                "transit": transit["classification"],
                "approximated_transit": approximated["classification"],
                "difference": {
                    "duration_seconds": (
                        duration_b - duration_a
                        if isinstance(duration_a, (int, float))
                        and isinstance(duration_b, (int, float))
                        else None
                    ),
                    "distance_meters": (
                        distance_b - distance_a
                        if isinstance(distance_a, (int, float))
                        and isinstance(distance_b, (int, float))
                        else None
                    ),
                    "leg_count": approximated["leg_count"] - transit["leg_count"],
                    "step_count": approximated["step_count"] - transit["step_count"],
                    "response_size_bytes": (
                        approximated["response_size_bytes"]
                        - transit["response_size_bytes"]
                    ),
                    "transit_instruction_types_changed": (
                        approximated["transit_instruction_types"]
                        != transit["transit_instruction_types"]
                    ),
                    "named_lines_changed": (
                        approximated["named_lines"] != transit["named_lines"]
                    ),
                    "named_stops_changed": (
                        approximated["named_stops"] != transit["named_stops"]
                    ),
                },
            }
        )
    return comparisons


def choose_recommendation(main_results: list[dict[str, Any]]) -> str:
    transit = [result for result in main_results if result["mode"] == "transit"]
    moscow = [
        result
        for result in transit
        if result["scenario"].startswith("nakhabino_")
    ]
    if transit and all(
        result["classification"] == "verified_timetable_route" for result in transit
    ):
        return "recommended_as_primary"
    if any(
        result["classification"] == "structured_transit_route_without_schedule"
        for result in moscow
    ):
        return "recommended_as_unscheduled_fallback"
    approximated_moscow = [
        result
        for result in main_results
        if result["mode"] == "approximated_transit"
        and result["scenario"].startswith("nakhabino_")
    ]
    if any(
        result["classification"] == "approximated_network_route"
        for result in approximated_moscow
    ):
        return "recommended_only_as_approximate_fallback"
    if main_results and all(
        result["classification"] in {"provider_error", "invalid_response"}
        for result in main_results
    ):
        return "inconclusive"
    return "not_recommended"


async def run_live(*, delay_seconds: float) -> dict[str, Any]:
    api_key = os.getenv("GEOAPIFY_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEOAPIFY_API_KEY is required for the live diagnostic")
    if delay_seconds < MIN_REQUEST_DELAY_SECONDS:
        raise ValueError(
            f"delay must be at least {MIN_REQUEST_DELAY_SECONDS} seconds"
        )
    base_url = normalize_base_url(
        os.getenv("GEOAPIFY_BASE_URL", DEFAULT_BASE_URL)
    )
    RAW_DIRECTORY.mkdir(parents=True, exist_ok=True)

    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=False) as client:
            runner = LiveRunner(
                client=client,
                base_url=base_url,
                api_key=api_key,
                delay_seconds=delay_seconds,
                raw_directory=RAW_DIRECTORY,
            )
            main_results: list[dict[str, Any]] = []
            main_payloads: dict[tuple[str, str], Any] = {}
            for scenario, mode, _params in build_main_matrix(api_key):
                summary, payload = await runner.execute(scenario, mode)
                main_results.append(summary)
                main_payloads[(scenario.name, mode)] = payload

            repeat_results: list[dict[str, Any]] = []
            for scenario in SCENARIOS:
                if scenario.name not in REPEAT_SCENARIOS:
                    continue
                repeated_summary, repeated_payload = await runner.execute(
                    scenario,
                    "transit",
                    suffix="repeat",
                )
                first_payload = main_payloads[(scenario.name, "transit")]
                repeat_results.append(
                    {
                        "scenario": scenario.name,
                        "mode": "transit",
                        "same_without_geometry_and_metadata": compare_repeat_payloads(
                            first_payload,
                            repeated_payload,
                        ),
                        "first_digest": repeat_digest(first_payload),
                        "repeat_digest": repeat_digest(repeated_payload),
                        "repeat_classification": repeated_summary["classification"],
                    }
                )

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "documentation_check": {
                "checked_on": date.today().isoformat(),
                "url": "https://apidocs.geoapify.com/docs/routing/",
                "documented_request_parameters": sorted(
                    DOCUMENTED_REQUEST_PARAMETERS
                ),
                "temporal_planning_parameters_documented": False,
                "unsupported_parameters_not_sent": sorted(
                    UNSUPPORTED_TEMPORAL_PARAMETERS
                ),
            },
            "request_count": runner.request_count,
            "estimated_credits": runner.request_count,
            "main_request_count": len(main_results),
            "repeat_request_count": len(repeat_results),
            "main_results": main_results,
            "repeat_results": repeat_results,
            "mode_comparisons": compare_modes(main_results),
            "recommendation": choose_recommendation(main_results),
            "temporary_raw_files_deleted": False,
        }
    finally:
        shutil.rmtree(RAW_DIRECTORY, ignore_errors=True)
        parent = RAW_DIRECTORY.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()

    report["temporary_raw_files_deleted"] = not RAW_DIRECTORY.exists()
    return report


def print_report(report: dict[str, Any]) -> None:
    print("scenario | mode | status | classification | distance | duration | legs | steps")
    for result in report["main_results"]:
        print(
            f"{result['scenario']} | {result['mode']} | {result['http_status']} | "
            f"{result['classification']} | {result['distance_meters']} | "
            f"{result['duration_seconds']} | {result['leg_count']} | "
            f"{result['step_count']}"
        )

    print("\nscenario | transit | approximated_transit | difference")
    for comparison in report["mode_comparisons"]:
        print(
            f"{comparison['scenario']} | {comparison['transit']} | "
            f"{comparison['approximated_transit']} | "
            f"{json.dumps(comparison['difference'], ensure_ascii=False)}"
        )

    print("\nRepeat checks")
    for repeat in report["repeat_results"]:
        print(
            f"{repeat['scenario']}: "
            f"same={repeat['same_without_geometry_and_metadata']}"
        )
    print(f"\napi_requests={report['request_count']}")
    print(f"estimated_credits={report['estimated_credits']}")
    print(f"temporary_raw_files_deleted={report['temporary_raw_files_deleted']}")
    print(f"recommendation={report['recommendation']}")
    print("compact_report_json=")
    print(json.dumps(report, ensure_ascii=False, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate Geoapify transit routing without production changes.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=MIN_REQUEST_DELAY_SECONDS,
        help="Delay between requests; values below 0.25 are rejected.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    report = await run_live(delay_seconds=args.delay_seconds)
    print_report(report)


if __name__ == "__main__":
    asyncio.run(main())

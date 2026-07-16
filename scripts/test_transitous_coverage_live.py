from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import sys
import tempfile
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
load_dotenv(ROOT / ".env")

from app.core.config import settings
from app.integrations.transitous import (
    TransitousError,
    TransitousHttpClient,
    TransitousResponseError,
)
from app.integrations.transitous.routing_policy import (
    TRANSIT_ACCESS_MODES,
    TRANSIT_DIRECT_MODES,
    TRANSIT_EGRESS_MODES,
    TRANSIT_MAX_ACCESS_SECONDS,
    TRANSIT_MAX_EGRESS_SECONDS,
)


MAX_PROVIDER_API_REQUESTS = 29
DEFAULT_DELAY_SECONDS = 0.5
SOURCES_URL = "https://transitous.org/sources/"
SOURCE_TERMS = (
    "russia",
    "moscow",
    "moskva",
    "nakhabino",
    "rzd",
    "mosgortrans",
)


@dataclass(frozen=True, slots=True)
class Point:
    key: str
    label: str
    latitude: float
    longitude: float
    timezone: str

    @property
    def coordinate(self) -> str:
        return f"{self.latitude:.7f},{self.longitude:.7f}"


@dataclass(frozen=True, slots=True)
class PlanScenario:
    name: str
    family: str
    variant: str
    from_place: str
    to_place: str
    endpoint_representation: str
    timezone: str
    hour: int
    transit_modes: tuple[str, ...] = ("TRANSIT",)
    access_seconds: int = TRANSIT_MAX_ACCESS_SECONDS
    radius: int | None = None


POINTS = {
    point.key: point
    for point in (
        Point(
            "berlin_alexanderplatz",
            "Berlin Alexanderplatz",
            52.5219,
            13.4132,
            "Europe/Berlin",
        ),
        Point(
            "berlin_hauptbahnhof",
            "Berlin Hauptbahnhof",
            52.5251,
            13.3694,
            "Europe/Berlin",
        ),
        Point(
            "nakhabino",
            "Nakhabino station",
            55.8415879,
            37.1849110,
            "Europe/Moscow",
        ),
        Point(
            "kurskaya",
            "Kurskaya metro",
            55.7588462,
            37.6580446,
            "Europe/Moscow",
        ),
        Point(
            "moscow_center",
            "Moscow center",
            55.751244,
            37.618423,
            "Europe/Moscow",
        ),
        Point(
            "arkhangelskoye",
            "Arkhangelskoye museum",
            55.7846853,
            37.2842631,
            "Europe/Moscow",
        ),
    )
}


@dataclass(slots=True)
class TransportCapture:
    url: str | None = None
    status_code: int | None = None

    def reset(self) -> None:
        self.url = None
        self.status_code = None

    async def on_request(self, request: httpx.Request) -> None:
        self.url = str(request.url)

    async def on_response(self, response: httpx.Response) -> None:
        self.status_code = response.status_code


class DiagnosticRunner:
    def __init__(
        self,
        client: TransitousHttpClient,
        capture: TransportCapture,
        *,
        delay_seconds: float,
        request_limit: int = MAX_PROVIDER_API_REQUESTS,
    ) -> None:
        self.client = client
        self.capture = capture
        self.delay_seconds = delay_seconds
        self.request_limit = request_limit
        self.records: list[dict[str, Any]] = []

    async def request(
        self,
        *,
        name: str,
        category: str,
        path: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        if len(self.records) >= self.request_limit:
            raise RuntimeError(
                f"Transitous diagnostic request limit exceeded: {self.request_limit}"
            )
        if self.records and self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)

        self.capture.reset()
        started = perf_counter()
        raw_response: dict[str, Any] | list[Any] | None = None
        error: dict[str, Any] | None = None
        try:
            raw_response = await self.client.get(path, params)
        except TransitousResponseError as exc:
            raw_response = exc.response_payload
            error = {
                "type": exc.__class__.__name__,
                "message": exc.message,
                "status_code": exc.status_code,
            }
        except TransitousError as exc:
            error = {
                "type": exc.__class__.__name__,
                "message": str(exc),
            }

        duration_ms = round((perf_counter() - started) * 1000, 1)
        url = self.capture.url
        parsed_url = httpx.URL(url) if url else None
        record = {
            "name": name,
            "category": category,
            "url": url,
            "path": parsed_url.path if parsed_url else path,
            "query_parameters": (
                dict(parsed_url.params.multi_items()) if parsed_url else params
            ),
            "http_status": self.capture.status_code,
            "duration_ms": duration_ms,
            "error": error,
            "raw_response": raw_response,
        }
        self.records.append(record)
        return record


def bbox_around(point: Point, *, half_size_metres: float = 750.0) -> dict[str, str]:
    latitude_delta = half_size_metres / 111_320.0
    longitude_delta = half_size_metres / (
        111_320.0 * math.cos(math.radians(point.latitude))
    )
    return {
        "min": (
            f"{point.latitude - latitude_delta:.7f},"
            f"{point.longitude + longitude_delta:.7f}"
        ),
        "max": (
            f"{point.latitude + latitude_delta:.7f},"
            f"{point.longitude - longitude_delta:.7f}"
        ),
        "grouped": "false",
    }


def haversine_metres(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    earth_radius = 6_371_000.0
    phi_a = math.radians(latitude_a)
    phi_b = math.radians(latitude_b)
    delta_phi = math.radians(latitude_b - latitude_a)
    delta_lambda = math.radians(longitude_b - longitude_a)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi_a)
        * math.cos(phi_b)
        * math.sin(delta_lambda / 2) ** 2
    )
    return earth_radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def normalize_stops(raw_response: Any, point: Point) -> list[dict[str, Any]]:
    if not isinstance(raw_response, list):
        return []
    stops: list[dict[str, Any]] = []
    for item in raw_response:
        if not isinstance(item, dict):
            continue
        latitude = item.get("lat")
        longitude = item.get("lon")
        if not isinstance(latitude, (int, float)) or not isinstance(
            longitude,
            (int, float),
        ):
            continue
        modes = item.get("modes")
        stops.append(
            {
                "stop_id": item.get("stopId"),
                "name": item.get("name"),
                "latitude": latitude,
                "longitude": longitude,
                "modes": modes if isinstance(modes, list) else [],
                "distance_metres": round(
                    haversine_metres(
                        point.latitude,
                        point.longitude,
                        float(latitude),
                        float(longitude),
                    ),
                    1,
                ),
            }
        )
    return sorted(stops, key=lambda stop: stop["distance_metres"])


def nearest_stop_id(area: dict[str, Any]) -> str | None:
    for stop in area.get("stops", []):
        stop_id = stop.get("stop_id")
        if isinstance(stop_id, str) and stop_id:
            return stop_id
    return None


def local_datetime(test_date: date, hour: int, timezone_name: str) -> datetime:
    return datetime.combine(
        test_date,
        time(hour=hour),
        tzinfo=ZoneInfo(timezone_name),
    )


def build_plan_scenarios(
    test_date: date,
    nearest_stop_ids: dict[str, str | None],
) -> list[PlanScenario]:
    del test_date
    berlin_from = POINTS["berlin_alexanderplatz"]
    berlin_to = POINTS["berlin_hauptbahnhof"]
    nakhabino = POINTS["nakhabino"]
    kurskaya = POINTS["kurskaya"]
    moscow_center = POINTS["moscow_center"]
    arkhangelskoye = POINTS["arkhangelskoye"]

    scenarios = [
        PlanScenario(
            "berlin_coordinate_12",
            "berlin",
            "baseline_12",
            berlin_from.coordinate,
            berlin_to.coordinate,
            "coordinate",
            berlin_from.timezone,
            12,
        ),
        PlanScenario(
            "moscow_center_to_kurskaya_12",
            "moscow_center_kurskaya",
            "baseline_12",
            moscow_center.coordinate,
            kurskaya.coordinate,
            "coordinate",
            moscow_center.timezone,
            12,
        ),
    ]

    for hour in (8, 12, 18):
        scenarios.append(
            PlanScenario(
                f"nakhabino_kurskaya_{hour:02d}_transit",
                "nakhabino_kurskaya",
                f"time_{hour:02d}",
                nakhabino.coordinate,
                kurskaya.coordinate,
                "coordinate",
                nakhabino.timezone,
                hour,
            )
        )
    scenarios.extend(
        [
            PlanScenario(
                "nakhabino_kurskaya_12_explicit_modes",
                "nakhabino_kurskaya",
                "explicit_modes",
                nakhabino.coordinate,
                kurskaya.coordinate,
                "coordinate",
                nakhabino.timezone,
                12,
                transit_modes=("SUBURBAN", "SUBWAY", "BUS"),
            ),
            PlanScenario(
                "nakhabino_kurskaya_12_access_1800",
                "nakhabino_kurskaya",
                "access_1800",
                nakhabino.coordinate,
                kurskaya.coordinate,
                "coordinate",
                nakhabino.timezone,
                12,
                access_seconds=1800,
            ),
            PlanScenario(
                "nakhabino_kurskaya_12_radius_500",
                "nakhabino_kurskaya",
                "radius_500",
                nakhabino.coordinate,
                kurskaya.coordinate,
                "coordinate",
                nakhabino.timezone,
                12,
                radius=500,
            ),
            PlanScenario(
                "nakhabino_kurskaya_12_radius_1000",
                "nakhabino_kurskaya",
                "radius_1000",
                nakhabino.coordinate,
                kurskaya.coordinate,
                "coordinate",
                nakhabino.timezone,
                12,
                radius=1000,
            ),
        ]
    )

    for hour in (8, 12, 18):
        scenarios.append(
            PlanScenario(
                f"nakhabino_arkhangelskoye_{hour:02d}_transit",
                "nakhabino_arkhangelskoye",
                f"time_{hour:02d}",
                nakhabino.coordinate,
                arkhangelskoye.coordinate,
                "coordinate",
                nakhabino.timezone,
                hour,
            )
        )
    scenarios.extend(
        [
            PlanScenario(
                "nakhabino_arkhangelskoye_12_access_1800",
                "nakhabino_arkhangelskoye",
                "access_1800",
                nakhabino.coordinate,
                arkhangelskoye.coordinate,
                "coordinate",
                nakhabino.timezone,
                12,
                access_seconds=1800,
            ),
            PlanScenario(
                "nakhabino_arkhangelskoye_12_radius_1000",
                "nakhabino_arkhangelskoye",
                "radius_1000",
                nakhabino.coordinate,
                arkhangelskoye.coordinate,
                "coordinate",
                nakhabino.timezone,
                12,
                radius=1000,
            ),
        ]
    )

    stop_pairs = (
        (
            "berlin_stop_ids_12",
            "berlin",
            "berlin_alexanderplatz",
            "berlin_hauptbahnhof",
            berlin_from.timezone,
        ),
        (
            "nakhabino_kurskaya_stop_ids_12",
            "nakhabino_kurskaya",
            "nakhabino",
            "kurskaya",
            nakhabino.timezone,
        ),
        (
            "nakhabino_arkhangelskoye_stop_ids_12",
            "nakhabino_arkhangelskoye",
            "nakhabino",
            "arkhangelskoye",
            nakhabino.timezone,
        ),
    )
    for name, family, from_key, to_key, timezone_name in stop_pairs:
        from_stop_id = nearest_stop_ids.get(from_key)
        to_stop_id = nearest_stop_ids.get(to_key)
        if from_stop_id and to_stop_id:
            scenarios.append(
                PlanScenario(
                    name,
                    family,
                    "stop_ids",
                    from_stop_id,
                    to_stop_id,
                    "stop_id",
                    timezone_name,
                    12,
                )
            )

    if len(scenarios) > 17:
        raise AssertionError("diagnostic plan matrix exceeded 17 requests")
    return scenarios


def plan_params(scenario: PlanScenario, test_date: date) -> dict[str, Any]:
    return {
        "fromPlace": scenario.from_place,
        "toPlace": scenario.to_place,
        "time": local_datetime(test_date, scenario.hour, scenario.timezone),
        "arriveBy": False,
        "transitModes": scenario.transit_modes,
        "preTransitModes": TRANSIT_ACCESS_MODES,
        "postTransitModes": TRANSIT_EGRESS_MODES,
        "directModes": TRANSIT_DIRECT_MODES,
        "maxPreTransitTime": scenario.access_seconds,
        "maxPostTransitTime": scenario.access_seconds,
        "maxTravelTime": 240,
        "numItineraries": 3,
        "maxItineraries": 3,
        "searchWindow": 900,
        "detailedLegs": False,
        "detailedTransfers": False,
        "timetableView": True,
        "language": "de" if scenario.timezone == "Europe/Berlin" else "ru",
        "radius": scenario.radius,
    }


def list_count(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def summarize_plan(
    scenario: PlanScenario,
    record: dict[str, Any],
) -> dict[str, Any]:
    raw_response = record.get("raw_response")
    response = raw_response if isinstance(raw_response, dict) else {}
    return {
        "name": scenario.name,
        "family": scenario.family,
        "variant": scenario.variant,
        "endpoint_representation": scenario.endpoint_representation,
        "transit_modes": list(scenario.transit_modes),
        "access_seconds": scenario.access_seconds,
        "radius": scenario.radius,
        "http_status": record.get("http_status"),
        "duration_ms": record.get("duration_ms"),
        "request_parameters": response.get("requestParameters"),
        "debug_output": response.get("debugOutput"),
        "normalized_from": response.get("from"),
        "normalized_to": response.get("to"),
        "itineraries_count": list_count(response.get("itineraries")),
        "direct_count": list_count(response.get("direct")),
        "error": record.get("error"),
        "request_record_index": None,
    }


def routes_by_name(plan_summaries: list[dict[str, Any]]) -> dict[str, int]:
    return {
        str(plan.get("name")): int(plan.get("itineraries_count") or 0)
        for plan in plan_summaries
    }


def classify_diagnostics(
    area_summaries: dict[str, dict[str, Any]],
    plan_summaries: list[dict[str, Any]],
) -> str:
    routes = routes_by_name(plan_summaries)
    if routes.get("berlin_coordinate_12", 0) == 0:
        return "integration_bug"

    russian_keys = ("nakhabino", "kurskaya", "moscow_center", "arkhangelskoye")
    russian_areas = [area_summaries.get(key, {}) for key in russian_keys]
    if sum(int(area.get("stops_count") or 0) for area in russian_areas) == 0:
        return "provider_coverage_unavailable"

    baseline_names = (
        "nakhabino_kurskaya_12_transit",
        "nakhabino_arkhangelskoye_12_transit",
    )
    baseline_has_route = any(routes.get(name, 0) > 0 for name in baseline_names)
    if not baseline_has_route and any(
        routes.get(name, 0) > 0
        for name in (
            "nakhabino_kurskaya_12_access_1800",
            "nakhabino_arkhangelskoye_12_access_1800",
        )
    ):
        return "access_policy_issue"
    if not baseline_has_route and any(
        routes.get(name, 0) > 0
        for name in (
            "nakhabino_kurskaya_12_radius_500",
            "nakhabino_kurskaya_12_radius_1000",
            "nakhabino_arkhangelskoye_12_radius_1000",
            "nakhabino_kurskaya_stop_ids_12",
            "nakhabino_arkhangelskoye_stop_ids_12",
        )
    ):
        return "coordinate_matching_issue"

    populated_areas = [
        area for area in russian_areas if int(area.get("stops_count") or 0) > 0
    ]
    if not populated_areas:
        return "provider_coverage_unavailable"
    if all(int(area.get("stoptimes_count") or 0) == 0 for area in populated_areas):
        return "provider_coverage_partial"
    if len(populated_areas) < len(russian_areas):
        return "provider_coverage_partial"

    russian_plans = [
        plan for plan in plan_summaries if plan.get("family") != "berlin"
    ]
    russian_route_count = sum(
        int(plan.get("itineraries_count") or 0) for plan in russian_plans
    )
    if russian_route_count and any(
        int(plan.get("itineraries_count") or 0) == 0 for plan in russian_plans
    ):
        return "provider_coverage_partial"
    return "inconclusive"


async def check_sources_catalog(user_agent: str) -> dict[str, Any]:
    started = perf_counter()
    try:
        async with httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=True,
            headers={"User-Agent": user_agent},
        ) as client:
            response = await client.get(SOURCES_URL)
        response.raise_for_status()
        text = response.text
        lowered = text.casefold()
        return {
            "url": str(response.url),
            "http_status": response.status_code,
            "duration_ms": round((perf_counter() - started) * 1000, 1),
            "documented_terms": {
                term: term.casefold() in lowered for term in SOURCE_TERMS
            },
            "documented_coverage": (
                "present"
                if any(term.casefold() in lowered for term in SOURCE_TERMS)
                else "not_found"
            ),
            "content_length": len(response.content),
            "content_sha256": hashlib.sha256(response.content).hexdigest(),
            "error": None,
        }
    except httpx.HTTPError as exc:
        return {
            "url": SOURCES_URL,
            "http_status": None,
            "duration_ms": round((perf_counter() - started) * 1000, 1),
            "documented_terms": {term: False for term in SOURCE_TERMS},
            "documented_coverage": "unavailable",
            "error": {
                "type": exc.__class__.__name__,
                "message": str(exc),
            },
        }


async def run_diagnostics(
    *,
    test_date: date,
    delay_seconds: float,
) -> dict[str, Any]:
    user_agent = settings.transitous_user_agent
    if not user_agent or not user_agent.strip():
        raise RuntimeError(
            "Set TRANSITOUS_USER_AGENT with application name, version and contact"
        )

    capture = TransportCapture()
    async with httpx.AsyncClient(
        base_url=settings.transitous_base_url,
        timeout=settings.transitous_timeout_seconds,
        trust_env=True,
        event_hooks={
            "request": [capture.on_request],
            "response": [capture.on_response],
        },
    ) as http_client:
        transitous_client = TransitousHttpClient(
            user_agent=user_agent,
            client=http_client,
        )
        runner = DiagnosticRunner(
            transitous_client,
            capture,
            delay_seconds=delay_seconds,
        )

        area_summaries: dict[str, dict[str, Any]] = {}
        for point in POINTS.values():
            record = await runner.request(
                name=f"stops_{point.key}",
                category="map_stops",
                path="/api/v6/map/stops",
                params={**bbox_around(point), "language": "ru,en"},
            )
            stops = normalize_stops(record.get("raw_response"), point)
            area_summaries[point.key] = {
                "label": point.label,
                "control_point": {
                    "latitude": point.latitude,
                    "longitude": point.longitude,
                },
                "stops_count": len(stops),
                "stops": stops,
                "nearest_stop_id": None,
                "stoptimes_count": 0,
                "map_request_record_index": len(runner.records) - 1,
                "stoptimes_request_record_index": None,
            }
            area_summaries[point.key]["nearest_stop_id"] = nearest_stop_id(
                area_summaries[point.key]
            )

        for key, area in area_summaries.items():
            stop_id = area.get("nearest_stop_id")
            if not isinstance(stop_id, str) or not stop_id:
                continue
            point = POINTS[key]
            record = await runner.request(
                name=f"stoptimes_{key}",
                category="stoptimes",
                path="/api/v6/stoptimes",
                params={
                    "stopId": stop_id,
                    "time": local_datetime(test_date, 12, point.timezone),
                    "n": 5,
                    "language": "ru,en",
                },
            )
            raw_response = record.get("raw_response")
            stop_times = (
                raw_response.get("stopTimes")
                if isinstance(raw_response, dict)
                else None
            )
            area["stoptimes_count"] = list_count(stop_times)
            area["stoptimes_request_record_index"] = len(runner.records) - 1

        nearest_ids = {
            key: area.get("nearest_stop_id")
            for key, area in area_summaries.items()
        }
        plan_summaries: list[dict[str, Any]] = []
        for scenario in build_plan_scenarios(test_date, nearest_ids):
            record = await runner.request(
                name=scenario.name,
                category="plan",
                path="/api/v6/plan",
                params=plan_params(scenario, test_date),
            )
            summary = summarize_plan(scenario, record)
            summary["request_record_index"] = len(runner.records) - 1
            plan_summaries.append(summary)

    if len(runner.records) > MAX_PROVIDER_API_REQUESTS:
        raise AssertionError("diagnostic exceeded its provider API request budget")
    sources = await check_sources_catalog(user_agent)
    classification = classify_diagnostics(area_summaries, plan_summaries)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "test_date": test_date.isoformat(),
        "provider_base_url": settings.transitous_base_url,
        "provider_api_request_count": len(runner.records),
        "provider_api_request_limit": MAX_PROVIDER_API_REQUESTS,
        "sources_catalog": sources,
        "observed_stops": area_summaries,
        "observed_stoptimes": {
            key: {
                "nearest_stop_id": area.get("nearest_stop_id"),
                "stoptimes_count": area.get("stoptimes_count"),
            }
            for key, area in area_summaries.items()
        },
        "observed_routing": plan_summaries,
        "classification": classification,
        "requests": runner.records,
    }


def print_report(report: dict[str, Any], output_path: Path) -> None:
    print("\nStops and stoptimes")
    print("area | stops | stoptimes | nearest_stop_id")
    for key, area in report["observed_stops"].items():
        print(
            f"{key} | {area['stops_count']} | {area['stoptimes_count']} | "
            f"{area['nearest_stop_id']}"
        )

    print("\nPlan matrix")
    print("scenario | status | itineraries | direct | duration_ms")
    for plan in report["observed_routing"]:
        print(
            f"{plan['name']} | {plan['http_status']} | "
            f"{plan['itineraries_count']} | {plan['direct_count']} | "
            f"{plan['duration_ms']}"
        )

    sources = report["sources_catalog"]
    print(f"\ndocumented_coverage={sources['documented_coverage']}")
    print(f"classification={report['classification']}")
    print(
        "provider_api_requests="
        f"{report['provider_api_request_count']}/"
        f"{report['provider_api_request_limit']}"
    )
    print(f"raw_diagnostics={output_path}")


def default_output_path() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path(tempfile.gettempdir()) / f"transitous-coverage-{timestamp}.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diagnose Transitous stop, timetable and routing coverage.",
    )
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=datetime.now(ZoneInfo("Europe/Moscow")).date() + timedelta(days=1),
        help="Service date in YYYY-MM-DD form; defaults to tomorrow in Moscow.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=DEFAULT_DELAY_SECONDS,
        help="Delay between provider API requests.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Raw JSON output path; defaults to the system temporary directory.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    if args.delay_seconds < 0:
        raise ValueError("--delay-seconds must be non-negative")
    output_path = args.output or default_output_path()
    report = await run_diagnostics(
        test_date=args.date,
        delay_seconds=args.delay_seconds,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print_report(report, output_path)


if __name__ == "__main__":
    asyncio.run(main())

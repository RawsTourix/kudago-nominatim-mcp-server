import asyncio
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app.application.executor import CommandExecutor
from app.core.db import AsyncSessionLocal, engine
from app.repositories.job_repository import JobRepository
from app.repositories.upstream_call_repository import UpstreamCallRepository
from app.schemas.routing import (
    StreetRouteProfile,
    StreetRouteRequest,
    TransitMode,
    TransitRouteRequest,
)


BERLIN_ALEXANDERPLATZ = (52.5219, 13.4132)
BERLIN_HAUPTBAHNHOF = (52.5251, 13.3694)
NAKHABINO_STATION = (55.8415879, 37.184911)
ARKHANGELSKOYE_MUSEUM = (55.7885844, 37.2859336)
MOSCOW_BELORUSSKY_STATION = (55.776397, 37.580345)
SHORT_STREET_DESTINATION = (55.8450, 37.1950)


@dataclass(frozen=True, slots=True)
class SmokeScenario:
    name: str
    command: str
    request: TransitRouteRequest | StreetRouteRequest
    expected_provider: str
    require_route: bool


async def _run_scenario(scenario: SmokeScenario) -> dict[str, Any]:
    payload = scenario.request.model_dump(mode="json")
    async with AsyncSessionLocal() as session:
        job = await JobRepository(session).create(
            command=scenario.command,
            input_payload=payload,
        )
        output = await CommandExecutor(session).run_payload(
            job_id=job.id,
            command=scenario.command,
            payload=payload,
            source="routing-live-smoke",
            endpoint=f"script://routing-live-smoke/{scenario.name}",
        )
        calls = await UpstreamCallRepository(session).get_by_job_id(job.id)
        if len(calls) != 1:
            raise AssertionError(
                f"{scenario.name}: expected one persisted upstream call, got {len(calls)}"
            )
        call = calls[0]
        if call.provider != scenario.expected_provider:
            raise AssertionError(
                f"{scenario.name}: unexpected provider {call.provider!r}"
            )
        if not isinstance(call.request_payload, dict):
            raise AssertionError(
                f"{scenario.name}: raw request_payload was not persisted"
            )
        if not isinstance(call.response_payload, dict):
            raise AssertionError(
                f"{scenario.name}: raw response_payload was not persisted"
            )

        _verify_persisted_upstream_call(scenario, call.request_payload)
        await session.commit()

        route_count = len(output.result_payload.get("routes", []))
        if scenario.require_route and not (
            output.status == "ok" and route_count > 0
        ):
            raise AssertionError(
                f"{scenario.name}: expected a verified route, "
                f"got status={output.status!r}, routes={route_count}"
            )
        response_collection = (
            "itineraries"
            if scenario.expected_provider == "transitous"
            else "routes"
        )
        raw_items = call.response_payload.get(response_collection)
        raw_count = len(raw_items) if isinstance(raw_items, list) else None
        print(
            f"{scenario.name}: status={output.status}, routes={route_count}, "
            f"raw_{response_collection}={raw_count}, "
            f"upstream_payloads=verified, job_id={job.id}"
        )
        return {
            "status": output.status,
            "route_count": route_count,
            "job_id": str(job.id),
        }


def _verify_persisted_upstream_call(
    scenario: SmokeScenario,
    request_payload: dict[str, Any],
) -> None:
    if scenario.expected_provider == "transitous":
        expected_modes = [
            mode.value
            for mode in scenario.request.transit_modes
        ] if scenario.request.transit_modes is not None else ["TRANSIT"]
        expected = {
            "transit_modes": expected_modes,
            "pre_transit_modes": ["WALK"],
            "post_transit_modes": ["WALK"],
            "direct_modes": [],
            "max_pre_transit_time": 900,
            "max_post_transit_time": 900,
        }
        for key, value in expected.items():
            if request_payload.get(key) != value:
                raise AssertionError(
                    f"{scenario.name}: persisted {key} does not match {value!r}"
                )
        return

    if request_payload.get("profile") != scenario.request.profile.value:
        raise AssertionError(
            f"{scenario.name}: persisted ORS profile does not match request"
        )
    if request_payload.get("geometry") is not False:
        raise AssertionError(
            f"{scenario.name}: persisted ORS request unexpectedly enabled geometry"
        )


def _transit_scenarios(route_time: datetime) -> list[SmokeScenario]:
    common = {
        "time": route_time,
        "max_travel_time_minutes": 240,
        "num_itineraries": 3,
        "language": "en",
    }
    return [
        SmokeScenario(
            name="transit-covered-all-provider-supported",
            command="routing.transit.plan",
            request=TransitRouteRequest(
                origin_lat=BERLIN_ALEXANDERPLATZ[0],
                origin_lon=BERLIN_ALEXANDERPLATZ[1],
                destination_lat=BERLIN_HAUPTBAHNHOF[0],
                destination_lon=BERLIN_HAUPTBAHNHOF[1],
                transit_modes=None,
                **common,
            ),
            expected_provider="transitous",
            require_route=True,
        ),
        SmokeScenario(
            name="transit-covered-explicit-suburban",
            command="routing.transit.plan",
            request=TransitRouteRequest(
                origin_lat=BERLIN_ALEXANDERPLATZ[0],
                origin_lon=BERLIN_ALEXANDERPLATZ[1],
                destination_lat=BERLIN_HAUPTBAHNHOF[0],
                destination_lon=BERLIN_HAUPTBAHNHOF[1],
                transit_modes=[TransitMode.SUBURBAN],
                **common,
            ),
            expected_provider="transitous",
            require_route=True,
        ),
        SmokeScenario(
            name="transit-nakhabino-arkhangelskoye",
            command="routing.transit.plan",
            request=TransitRouteRequest(
                origin_lat=NAKHABINO_STATION[0],
                origin_lon=NAKHABINO_STATION[1],
                destination_lat=ARKHANGELSKOYE_MUSEUM[0],
                destination_lon=ARKHANGELSKOYE_MUSEUM[1],
                transit_modes=None,
                **common,
            ),
            expected_provider="transitous",
            require_route=False,
        ),
        SmokeScenario(
            name="transit-nakhabino-moscow",
            command="routing.transit.plan",
            request=TransitRouteRequest(
                origin_lat=NAKHABINO_STATION[0],
                origin_lon=NAKHABINO_STATION[1],
                destination_lat=MOSCOW_BELORUSSKY_STATION[0],
                destination_lon=MOSCOW_BELORUSSKY_STATION[1],
                transit_modes=None,
                **common,
            ),
            expected_provider="transitous",
            require_route=False,
        ),
    ]


def _street_scenarios() -> list[SmokeScenario]:
    return [
        SmokeScenario(
            name=f"ors-short-{profile.value}",
            command="routing.street.plan",
            request=StreetRouteRequest(
                origin_lat=NAKHABINO_STATION[0],
                origin_lon=NAKHABINO_STATION[1],
                destination_lat=SHORT_STREET_DESTINATION[0],
                destination_lon=SHORT_STREET_DESTINATION[1],
                profile=profile,
                include_geometry=False,
            ),
            expected_provider="openrouteservice",
            require_route=True,
        )
        for profile in (
            StreetRouteProfile.WALKING,
            StreetRouteProfile.CYCLING,
            StreetRouteProfile.DRIVING,
        )
    ]


async def main() -> None:
    if not os.getenv("TRANSITOUS_USER_AGENT", "").strip():
        raise RuntimeError(
            "Set TRANSITOUS_USER_AGENT with application name, version and contact"
        )
    if not os.getenv("OPENROUTESERVICE_API_KEY", "").strip():
        raise RuntimeError("Set OPENROUTESERVICE_API_KEY for the live smoke")

    route_time = datetime.now(timezone.utc) + timedelta(days=1)
    results: dict[str, dict[str, Any]] = {}
    try:
        for scenario in [*_street_scenarios(), *_transit_scenarios(route_time)]:
            results[scenario.name] = await _run_scenario(scenario)
    finally:
        await engine.dispose()

    moscow = results["transit-nakhabino-moscow"]
    if moscow["status"] == "ok" and moscow["route_count"] > 0:
        print("moscow_coverage=confirmed_for_exact_nakhabino_moscow_query")
    else:
        print("moscow_coverage=unknown_from_plan_response")


if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import os
import socket
import sys
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from arq.worker import Worker
from dotenv import load_dotenv
from fastmcp import Client
import httpx
from sqlalchemy import func, select
import uvicorn


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app.application.executor import CommandExecutor
from app.core.config import settings
from app.core.db import AsyncSessionLocal, engine
from app.core.redis import create_arq_pool
from app.main import app
from app.models.api_request import ApiRequest
from app.models.job import Job
from app.models.upstream_call import UpstreamCall
from app.repositories.job_repository import JobRepository
from app.repositories.upstream_call_repository import UpstreamCallRepository
from app.schemas.routing import (
    StreetRouteProfile,
    StreetRouteRequest,
    TransitMode,
    TransitRouteRequest,
)
from app.services.job_service import JobService
from app.workers.tasks import process_command_job


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


async def _run_mcp_http_e2e(route_time: datetime) -> None:
    worker_redis = await create_arq_pool(settings.redis_url)
    worker = Worker(
        [process_command_job],
        redis_pool=worker_redis,
        handle_signals=False,
        poll_delay=0.05,
        job_timeout=settings.arq_job_timeout_seconds,
        keep_result=3600,
    )
    worker_task = asyncio.create_task(worker.async_run())
    server_socket = _create_server_socket()
    host, port = server_socket.getsockname()[:2]
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=host,
            port=port,
            lifespan="on",
            log_level="warning",
        )
    )
    server_task = asyncio.create_task(server.serve(sockets=[server_socket]))
    base_url = f"http://{host}:{port}"

    transit_arguments = {
        "origin": {
            "label": "Berlin Alexanderplatz",
            "latitude": BERLIN_ALEXANDERPLATZ[0],
            "longitude": BERLIN_ALEXANDERPLATZ[1],
        },
        "destination": {
            "label": "Berlin Hauptbahnhof",
            "latitude": BERLIN_HAUPTBAHNHOF[0],
            "longitude": BERLIN_HAUPTBAHNHOF[1],
        },
        "departure_time": route_time.isoformat(),
        "max_routes": 3,
    }
    street_arguments = {
        "origin": {
            "label": "Nakhabino station",
            "latitude": NAKHABINO_STATION[0],
            "longitude": NAKHABINO_STATION[1],
        },
        "destination": {
            "label": "Nearby street point",
            "latitude": SHORT_STREET_DESTINATION[0],
            "longitude": SHORT_STREET_DESTINATION[1],
        },
        "travel_mode": "walking",
    }
    no_route_arguments = {
        "origin": {
            "label": "Nakhabino station",
            "latitude": NAKHABINO_STATION[0],
            "longitude": NAKHABINO_STATION[1],
        },
        "destination": {
            "label": "Arkhangelskoye museum",
            "latitude": ARKHANGELSKOYE_MUSEUM[0],
            "longitude": ARKHANGELSKOYE_MUSEUM[1],
        },
        "departure_time": route_time.isoformat(),
        "max_routes": 3,
    }

    try:
        await _wait_for_http_health(base_url, server, server_task)
        async with Client(f"{base_url}/mcp", timeout=180.0) as client:
            tools = {tool.name: tool for tool in await client.list_tools()}
            transit_schema = tools["plan_public_transport"].inputSchema
            properties = transit_schema["properties"]
            if not {"transport_modes", "max_routes"} <= properties.keys():
                raise AssertionError("live MCP schema is missing renamed transit fields")
            if {"modes", "limit"} & properties.keys():
                raise AssertionError("live MCP schema still exposes old transit fields")
            required_time_text = (
                "Exactly one of departure_time and arrival_time is required."
            )
            for time_field in ("departure_time", "arrival_time"):
                if required_time_text not in properties[time_field]["description"]:
                    raise AssertionError(
                        f"live MCP schema does not explain required {time_field}"
                    )
            if len(transit_schema.get("oneOf", [])) != 2:
                raise AssertionError(
                    "live MCP schema does not enforce exactly one routing time"
                )

            persistence_before = await _routing_persistence_counts()
            missing_time = await client.call_tool(
                "plan_public_transport",
                {
                    key: value
                    for key, value in transit_arguments.items()
                    if key != "departure_time"
                },
                timeout=180.0,
            )
            both_times = await client.call_tool(
                "plan_public_transport",
                {
                    **transit_arguments,
                    "arrival_time": (route_time + timedelta(hours=1)).isoformat(),
                },
                timeout=180.0,
            )
            _verify_mcp_validation_error(missing_time.data)
            _verify_mcp_validation_error(both_times.data)
            persistence_after = await _routing_persistence_counts()
            if persistence_after != persistence_before:
                raise AssertionError(
                    "invalid MCP routing calls created a job or upstream call"
                )

            transit = await client.call_tool(
                "plan_public_transport",
                transit_arguments,
                timeout=180.0,
            )
            street = await client.call_tool(
                "plan_street_route",
                street_arguments,
                timeout=180.0,
            )
            no_route = await client.call_tool(
                "plan_public_transport",
                no_route_arguments,
                timeout=180.0,
            )
    finally:
        server.should_exit = True
        try:
            await _await_bounded_shutdown(server_task, "Uvicorn server")
        finally:
            try:
                await worker.close()
                await _await_bounded_shutdown(
                    worker_task,
                    "arq worker",
                    cancelled_is_expected=True,
                )
            finally:
                server_socket.close()

    transit_result = transit.data
    street_result = street.data
    no_route_result = no_route.data
    _verify_mcp_result(
        transit_result,
        result_kind="public_transport_routes",
        origin_label="Berlin Alexanderplatz",
        destination_label="Berlin Hauptbahnhof",
    )
    _verify_mcp_result(
        street_result,
        result_kind="street_route",
        origin_label="Nakhabino station",
        destination_label="Nearby street point",
    )
    if transit_result["data"]["request"]["transport_modes"] is not None:
        raise AssertionError("omitted transport_modes was not preserved as null")
    if (
        transit_result["data"]["request"]["transport_mode_policy"]
        != "all_provider_supported"
    ):
        raise AssertionError("unexpected live MCP transport mode policy")
    if street_result["data"]["request"]["travel_mode"] != "walking":
        raise AssertionError("unexpected live MCP street travel mode")
    _verify_mcp_no_route(no_route_result)

    await _verify_mcp_job(
        transit_result,
        expected_request_text=(
            "Berlin Alexanderplatz (52.5219,13.4132) -> "
            "Berlin Hauptbahnhof (52.5251,13.3694)"
        ),
    )
    await _verify_mcp_job(
        street_result,
        expected_request_text=(
            "Nakhabino station (55.8415879,37.184911) -> "
            "Nearby street point (55.845,37.195)"
        ),
    )
    await _verify_mcp_job(
        no_route_result,
        expected_request_text=(
            "Nakhabino station (55.8415879,37.184911) -> "
            "Arkhangelskoye museum (55.7885844,37.2859336)"
        ),
    )
    print(
        "mcp-e2e-public-transport: "
        f"status={transit_result['data']['result_status']}, "
        f"routes={len(transit_result['data']['routes'])}, "
        f"job_id={transit_result['job_id']}"
    )
    print(
        "mcp-e2e-street-walking: "
        f"status={street_result['data']['result_status']}, "
        f"routes={len(street_result['data']['routes'])}, "
        f"job_id={street_result['job_id']}"
    )
    print(
        "mcp-e2e-public-transport-no-route: "
        f"diagnostic={no_route_result['data']['diagnostic']['code']}, "
        f"retry_hints={len(no_route_result['data']['retry_hints'])}, "
        f"job_id={no_route_result['job_id']}"
    )


def _create_server_socket() -> socket.socket:
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(("127.0.0.1", 0))
    server_socket.listen(2048)
    server_socket.setblocking(False)
    return server_socket


async def _wait_for_http_health(
    base_url: str,
    server: uvicorn.Server,
    server_task: asyncio.Task[bool | None],
) -> None:
    deadline = asyncio.get_running_loop().time() + 15.0
    while not server.started:
        if server_task.done():
            await server_task
            raise RuntimeError("Uvicorn stopped before becoming ready")
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("Uvicorn did not become ready within 15 seconds")
        await asyncio.sleep(0.05)

    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(f"{base_url}/api/v1/health")
    response.raise_for_status()
    if response.json() != {"status": "ok"}:
        raise AssertionError("HTTP health endpoint returned bad data")


async def _await_bounded_shutdown(
    task: asyncio.Task[Any],
    component: str,
    *,
    cancelled_is_expected: bool = False,
) -> None:
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=15.0)
    except asyncio.CancelledError:
        if not cancelled_is_expected:
            raise
    except TimeoutError:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        raise TimeoutError(f"{component} did not stop within 15 seconds")


async def _routing_persistence_counts() -> tuple[int, int]:
    async with AsyncSessionLocal() as session:
        job_count = await session.scalar(select(func.count()).select_from(Job))
        upstream_count = await session.scalar(
            select(func.count()).select_from(UpstreamCall)
        )
    return int(job_count or 0), int(upstream_count or 0)


def _verify_mcp_validation_error(result: dict[str, Any]) -> None:
    if result.get("status") != "error":
        raise AssertionError(f"invalid MCP call did not return an error: {result!r}")
    if result.get("error_type") != "validation_error":
        raise AssertionError(f"invalid MCP call returned a wrong envelope: {result!r}")
    if result.get("job_id") is not None:
        raise AssertionError("invalid MCP call unexpectedly returned a job_id")
    if not isinstance(result.get("details"), list) or not result["details"]:
        raise AssertionError("invalid MCP call returned no validation details")


def _verify_mcp_result(
    result: dict[str, Any],
    *,
    result_kind: str,
    origin_label: str,
    destination_label: str,
) -> None:
    if result.get("status") != "ok":
        raise AssertionError(f"live MCP call failed: {result!r}")
    data = result.get("data")
    if not isinstance(data, dict) or data.get("result_kind") != result_kind:
        raise AssertionError(f"live MCP returned unexpected data: {data!r}")
    if not data.get("route_verified") or not data.get("routes"):
        raise AssertionError(f"live MCP returned no verified route: {data!r}")
    request = data.get("request")
    if not isinstance(request, dict):
        raise AssertionError("live MCP result has no request summary")
    if request["origin"].get("label") != origin_label:
        raise AssertionError("live MCP result lost the origin label")
    if request["destination"].get("label") != destination_label:
        raise AssertionError("live MCP result lost the destination label")


def _verify_mcp_no_route(result: dict[str, Any]) -> None:
    if result.get("status") != "ok" or result.get("result_status") != "no_route":
        raise AssertionError(f"live MCP no-route call failed: {result!r}")
    data = result.get("data")
    if not isinstance(data, dict):
        raise AssertionError("live MCP no-route result has no data")
    if data.get("route_verified") is not False or data.get("routes") != []:
        raise AssertionError("live MCP no-route result claims a verified route")
    diagnostic = data.get("diagnostic")
    if not isinstance(diagnostic, dict) or diagnostic.get("code") != (
        "provider_returned_no_itineraries"
    ):
        raise AssertionError("live MCP no-route diagnostic was not serialized")
    hints = data.get("retry_hints")
    if not isinstance(hints, list) or not all(
        isinstance(hint, dict) and {"code", "message"} <= hint.keys()
        for hint in hints
    ):
        raise AssertionError("live MCP no-route retry hints are not structured")
    hint_codes = {hint["code"] for hint in hints}
    if "check_walking_access_limit" not in hint_codes:
        raise AssertionError("live MCP no-route response lost walking-limit guidance")


async def _verify_mcp_job(
    result: dict[str, Any],
    *,
    expected_request_text: str,
) -> None:
    job_id = UUID(result["job_id"])
    async with AsyncSessionLocal() as session:
        job = await JobService(session).get_by_id(job_id)
        if job is None or job.status != "succeeded":
            raise AssertionError(f"live MCP job did not succeed: {job_id}")
        if job.queue_job_id != f"{job.command}:{job_id}":
            raise AssertionError("live MCP job does not contain arq queue metadata")
        api_request = await session.get(ApiRequest, job.api_request_id)
        if api_request is None or api_request.request_text != expected_request_text:
            raise AssertionError("live MCP request_text did not preserve labels")
        upstream_calls = await UpstreamCallRepository(session).get_by_job_id(job_id)
        if len(upstream_calls) != 1:
            raise AssertionError("live MCP job did not persist one upstream call")


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
        await _run_mcp_http_e2e(route_time)
    finally:
        await engine.dispose()

    moscow = results["transit-nakhabino-moscow"]
    if moscow["status"] == "ok" and moscow["route_count"] > 0:
        print("moscow_coverage=confirmed_for_exact_nakhabino_moscow_query")
    else:
        print("moscow_coverage=unknown_from_plan_response")


if __name__ == "__main__":
    asyncio.run(main())

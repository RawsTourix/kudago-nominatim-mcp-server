from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.contracts import CommandOutput, ExecutionContext
from app.application.executor import CommandExecutor
from app.application.handlers.street_routing import StreetRoutingHandler
from app.application.handlers.transit_routing import TransitRoutingHandler
from app.integrations.openrouteservice import OpenRouteServiceResponseError
from app.integrations.transitous import (
    TransitousInvalidResponseError,
    TransitousResponseError,
)
from app.schemas.routing import (
    StreetRouteRequest,
    TransitMode,
    TransitRouteRequest,
)
from app.services.street_routing_service import StreetRoutingService
from app.services.transit_routing_service import (
    DEFAULT_TRANSIT_MODES,
    TransitRoutingService,
)


def transit_request(**overrides):
    payload = {
        "origin_lat": 52.5200,
        "origin_lon": 13.4050,
        "destination_lat": 52.5100,
        "destination_lon": 13.3900,
        "time": datetime(2026, 7, 12, 18, 40, tzinfo=timezone.utc),
    }
    payload.update(overrides)
    return TransitRouteRequest(**payload)


def street_request(**overrides):
    payload = {
        "origin_lat": 55.842,
        "origin_lon": 37.180,
        "destination_lat": 55.850,
        "destination_lon": 37.195,
    }
    payload.update(overrides)
    return StreetRouteRequest(**payload)


def transit_payload():
    return {
        "itineraries": [
            {
                "startTime": "2026-07-12T18:40:00+02:00",
                "endTime": "2026-07-12T19:18:00+02:00",
                "duration": 2280,
                "transfers": 1,
                "legs": [
                    {
                        "mode": "WALK",
                        "from": {"name": "Origin", "lat": 52.52, "lon": 13.405},
                        "to": {"name": "Stop A", "lat": 52.519, "lon": 13.4},
                        "startTime": "2026-07-12T18:40:00+02:00",
                        "endTime": "2026-07-12T18:47:00+02:00",
                        "scheduledStartTime": "2026-07-12T18:40:00+02:00",
                        "scheduledEndTime": "2026-07-12T18:47:00+02:00",
                        "duration": 420,
                        "distance": 510,
                        "realTime": False,
                        "cancelled": False,
                        "interlineWithPreviousLeg": False,
                    },
                    {
                        "mode": "SUBWAY",
                        "from": {"name": "Stop A", "lat": 52.519, "lon": 13.4},
                        "to": {"name": "Stop B", "lat": 52.511, "lon": 13.391},
                        "startTime": "2026-07-12T18:50:00+02:00",
                        "endTime": "2026-07-12T19:15:00+02:00",
                        "scheduledStartTime": "2026-07-12T18:48:00+02:00",
                        "scheduledEndTime": "2026-07-12T19:13:00+02:00",
                        "duration": 1500,
                        "routeShortName": "U2",
                        "routeLongName": "Pankow - Ruhleben",
                        "headsign": "Ruhleben",
                        "agencyName": "BVG",
                        "realTime": True,
                        "cancelled": False,
                    },
                ],
            }
        ]
    }


def street_payload(*, geometry=True):
    return {
        "bbox": [37.18, 55.84, 37.20, 55.86],
        "routes": [
            {
                "summary": {"distance": 1840.5, "duration": 1420.0},
                "segments": [
                    {
                        "distance": 1840.5,
                        "duration": 1420.0,
                        "steps": [
                            {
                                "instruction": "Head north",
                                "name": "Main Street",
                                "distance": 120.0,
                                "duration": 90.0,
                                "type": 11,
                            }
                        ],
                    }
                ],
                "geometry": "encoded-polyline" if geometry else None,
            }
        ],
        "metadata": {"attribution": "openrouteservice.org"},
    }


@pytest.mark.asyncio
async def test_transit_service_normalizes_itinerary_and_tracks_call():
    client = SimpleNamespace(get=AsyncMock(return_value=transit_payload()))
    service = TransitRoutingService(SimpleNamespace(), client=client)
    service.upstream_call_repo = SimpleNamespace(create=AsyncMock())

    result = await service.plan_route(job_id=uuid4(), request=transit_request())

    assert result["status"] == "ok"
    assert result["returned"] == 1
    route = result["routes"][0]
    assert route["has_realtime_data"] is True
    assert route["has_cancellations"] is False
    assert route["legs"][0]["mode"] == "WALK"
    assert route["legs"][1]["route_short_name"] == "U2"
    assert route["legs"][1]["headsign"] == "Ruhleben"
    assert route["legs"][1]["scheduled_departure_time"].endswith("+02:00")
    tracked = service.upstream_call_repo.create.await_args.kwargs
    assert tracked["success"] is True
    assert tracked["provider"] == "transitous"
    assert tracked["url_path"] == "/api/v6/plan"
    sent_params = client.get.await_args.args[1]
    assert sent_params["transitModes"] == [
        mode.value for mode in DEFAULT_TRANSIT_MODES
    ]
    assert "TRANSIT" not in sent_params["transitModes"]


@pytest.mark.asyncio
async def test_transit_service_treats_explicit_transit_as_safe_alias():
    client = SimpleNamespace(get=AsyncMock(return_value={"itineraries": []}))
    service = TransitRoutingService(SimpleNamespace(), client=client)
    service.upstream_call_repo = SimpleNamespace(create=AsyncMock())

    result = await service.plan_route(
        job_id=uuid4(),
        request=transit_request(transit_modes=[TransitMode.TRANSIT]),
    )

    expected = [mode.value for mode in DEFAULT_TRANSIT_MODES]
    assert result["query"]["transit_modes"] == expected
    assert client.get.await_args.args[1]["transitModes"] == expected


def test_transit_service_handles_empty_and_missing_optional_fields():
    request = transit_request(num_itineraries=2)
    no_route = TransitRoutingService._normalize(
        {"itineraries": []}, request, ["TRANSIT"]
    )
    sparse = TransitRoutingService._normalize(
        {"itineraries": [{"legs": [{}]}]}, request, ["TRANSIT"]
    )

    assert no_route["status"] == "no_route"
    assert no_route["routes"] == []
    assert sparse["routes"][0]["departure_time"] is None
    assert sparse["routes"][0]["legs"][0]["route_short_name"] is None
    assert sparse["routes"][0]["legs"][0]["from"] == {
        "name": None,
        "lat": None,
        "lon": None,
        "stop_id": None,
        "track": None,
        "scheduled_track": None,
        "cancelled": None,
        "pickup_type": None,
        "dropoff_type": None,
        "alerts": [],
    }


def test_transit_service_collects_and_deduplicates_place_warnings():
    alert = {
        "code": "alert-1",
        "cause": "TECHNICAL_PROBLEM",
        "effect": "SIGNIFICANT_DELAYS",
        "severityLevel": "SEVERE",
        "headerText": "Service disruption",
        "descriptionText": "Expect delays",
        "url": "https://example.test/alert-1",
    }
    changed_stop = {
        "name": "Stop A",
        "lat": 52.519,
        "lon": 13.4,
        "stopId": "de:stop-a",
        "track": "2",
        "scheduledTrack": "1",
        "cancelled": True,
        "pickupType": "NOT_ALLOWED",
        "alerts": [alert],
    }
    raw = {
        "itineraries": [
            {
                "legs": [
                    {"from": {"name": "Origin"}, "to": changed_stop},
                    {
                        "from": changed_stop,
                        "to": {"name": "Destination"},
                        "intermediateStops": [
                            {
                                "name": "Stop B",
                                "stopId": "de:stop-b",
                                "dropoffType": "NOT_ALLOWED",
                            }
                        ],
                    },
                ]
            }
        ]
    }

    result = TransitRoutingService._normalize(
        raw,
        transit_request(),
        [mode.value for mode in DEFAULT_TRANSIT_MODES],
    )

    route = result["routes"][0]
    stop = route["legs"][0]["to"]
    assert stop["stop_id"] == "de:stop-a"
    assert stop["track"] == "2"
    assert stop["scheduled_track"] == "1"
    assert stop["alerts"][0]["effect"] == "SIGNIFICANT_DELAYS"
    assert route["has_cancellations"] is True
    assert route["legs"][1]["intermediate_stops"][0]["stop_id"] == "de:stop-b"
    warning_types = [warning["type"] for warning in route["warnings"]]
    assert warning_types.count("service_alert") == 1
    assert warning_types.count("platform_change") == 1
    assert warning_types.count("stop_cancelled") == 1
    assert warning_types.count("pickup_not_allowed") == 1
    assert warning_types.count("dropoff_not_allowed") == 1
    assert result["warnings"] == route["warnings"]


def test_transit_service_rejects_naive_provider_time():
    with pytest.raises(TransitousInvalidResponseError, match="timezone"):
        TransitRoutingService._normalize(
            {
                "itineraries": [
                    {"startTime": "2026-07-12T18:40:00", "legs": []}
                ]
            },
            transit_request(),
            ["TRANSIT"],
        )


@pytest.mark.asyncio
async def test_transit_service_tracks_provider_failure():
    error = TransitousResponseError(
        message="unavailable",
        status_code=500,
        reason_phrase="Server Error",
        response_text="unavailable",
        response_payload={"message": "unavailable"},
    )
    client = SimpleNamespace(get=AsyncMock(side_effect=error))
    service = TransitRoutingService(SimpleNamespace(), client=client)
    service.upstream_call_repo = SimpleNamespace(create=AsyncMock())

    with pytest.raises(TransitousResponseError):
        await service.plan_route(job_id=uuid4(), request=transit_request())

    tracked = service.upstream_call_repo.create.await_args.kwargs
    assert tracked["success"] is False
    assert tracked["response_status_code"] == 500


@pytest.mark.asyncio
async def test_transit_service_tracks_invalid_structure_as_failure():
    client = SimpleNamespace(get=AsyncMock(return_value={"unexpected": True}))
    service = TransitRoutingService(SimpleNamespace(), client=client)
    service.upstream_call_repo = SimpleNamespace(create=AsyncMock())

    with pytest.raises(TransitousInvalidResponseError):
        await service.plan_route(job_id=uuid4(), request=transit_request())

    tracked = service.upstream_call_repo.create.await_args.kwargs
    assert tracked["success"] is False
    assert tracked["response_status_code"] == 200
    assert tracked["response_payload"] == {"unexpected": True}


@pytest.mark.asyncio
async def test_street_service_normalizes_summary_segments_and_geometry():
    client = SimpleNamespace(post=AsyncMock(return_value=street_payload()))
    service = StreetRoutingService(SimpleNamespace(), client=client)
    service.upstream_call_repo = SimpleNamespace(create=AsyncMock())

    result = await service.plan_route(
        job_id=uuid4(),
        request=street_request(include_geometry=True),
    )

    assert result["status"] == "ok"
    assert result["profile"] == "walking"
    route = result["routes"][0]
    assert route["distance_meters"] == 1840.5
    assert route["duration_seconds"] == 1420.0
    assert route["segments"][0]["steps"][0]["type"] == 11
    assert route["geometry"] == "encoded-polyline"
    assert result["attribution"] == [{"name": "openrouteservice.org"}]


def test_street_service_omits_steps_and_geometry_when_disabled():
    result = StreetRoutingService._normalize(
        street_payload(),
        street_request(include_instructions=False, include_geometry=False),
    )
    route = result["routes"][0]
    assert route["segments"][0]["steps"] == []
    assert route["geometry"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("error_code", [2009, 2016])
async def test_street_service_converts_known_provider_errors_to_no_route(error_code):
    error = OpenRouteServiceResponseError(
        message="route not found",
        status_code=404,
        reason_phrase="Not Found",
        response_text="route not found",
        response_payload={
            "error": {"code": error_code, "message": "route not found"}
        },
    )
    client = SimpleNamespace(post=AsyncMock(side_effect=error))
    service = StreetRoutingService(SimpleNamespace(), client=client)
    service.upstream_call_repo = SimpleNamespace(create=AsyncMock())

    result = await service.plan_route(job_id=uuid4(), request=street_request())

    assert result["status"] == "no_route"
    assert result["routes"] == []
    tracked = service.upstream_call_repo.create.await_args.kwargs
    assert tracked["success"] is False
    assert "api_key" not in str(tracked["request_payload"]).lower()


@pytest.mark.asyncio
async def test_street_service_does_not_mask_5xx_as_no_route():
    error = OpenRouteServiceResponseError(
        message="internal failure",
        status_code=500,
        reason_phrase="Server Error",
        response_text="internal failure",
        response_payload={"error": {"code": 2009, "message": "failure"}},
    )
    client = SimpleNamespace(post=AsyncMock(side_effect=error))
    service = StreetRoutingService(SimpleNamespace(), client=client)
    service.upstream_call_repo = SimpleNamespace(create=AsyncMock())

    with pytest.raises(OpenRouteServiceResponseError):
        await service.plan_route(job_id=uuid4(), request=street_request())


@pytest.mark.asyncio
async def test_street_service_does_not_mask_bare_404_as_no_route():
    error = OpenRouteServiceResponseError(
        message="endpoint not found",
        status_code=404,
        reason_phrase="Not Found",
        response_text="endpoint not found",
        response_payload={"error": "Not Found"},
    )
    client = SimpleNamespace(post=AsyncMock(side_effect=error))
    service = StreetRoutingService(SimpleNamespace(), client=client)
    service.upstream_call_repo = SimpleNamespace(create=AsyncMock())

    with pytest.raises(OpenRouteServiceResponseError):
        await service.plan_route(job_id=uuid4(), request=street_request())


@pytest.mark.asyncio
async def test_routing_handlers_build_transport_neutral_outputs():
    transit_handler = TransitRoutingHandler.__new__(TransitRoutingHandler)
    transit_handler.routing_service = SimpleNamespace(
        plan_route=AsyncMock(
            return_value={
                "status": "no_route",
                "provider": "transitous",
                "returned": 0,
                "routes": [],
            }
        )
    )
    street_handler = StreetRoutingHandler.__new__(StreetRoutingHandler)
    street_handler.routing_service = SimpleNamespace(
        plan_route=AsyncMock(
            return_value={
                "status": "ok",
                "provider": "openrouteservice",
                "profile": "walking",
                "returned": 1,
                "routes": [{"distance_meters": 100}],
            }
        )
    )

    transit_output = await transit_handler.run(
        ExecutionContext(uuid4(), "routing.transit.plan", "test"),
        transit_request().model_dump(mode="json"),
    )
    street_output = await street_handler.run(
        ExecutionContext(uuid4(), "routing.street.plan", "test"),
        street_request().model_dump(mode="json"),
    )

    assert transit_output.status == "no_route"
    assert transit_output.result_type == "routing.transit.plan"
    assert transit_output.items == []
    assert {event.event_type for event in transit_output.events} == {
        "routing_request_prepared",
        "routing_no_route",
        "routing_normalized",
    }
    assert street_output.result_type == "routing.street.plan"
    assert street_output.items == [{"distance_meters": 100}]
    assert street_output.meta["provider"] == "openrouteservice"


@pytest.mark.asyncio
async def test_no_route_is_persisted_as_succeeded_job():
    job = SimpleNamespace(id=uuid4(), command="routing.transit.plan")
    output = CommandOutput(
        status="no_route",
        result_type="routing.transit.plan",
        items=[],
        meta={"status": "no_route", "provider": "transitous", "returned": 0},
        result_payload={
            "status": "no_route",
            "provider": "transitous",
            "returned": 0,
            "routes": [],
        },
    )
    executor = CommandExecutor(SimpleNamespace())
    executor.job_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=job),
        mark_running=AsyncMock(),
        mark_succeeded=AsyncMock(),
        mark_failed=AsyncMock(),
        add_event=AsyncMock(),
    )
    executor.result_repo = SimpleNamespace(create=AsyncMock())
    executor._dispatch = AsyncMock(return_value=output)

    actual = await executor.run_payload(
        job_id=job.id,
        command=job.command,
        payload={},
        source="test",
    )

    assert actual.status == "no_route"
    executor.job_repo.mark_succeeded.assert_awaited_once_with(
        job,
        result_payload=output.result_payload,
    )
    executor.job_repo.mark_failed.assert_not_awaited()

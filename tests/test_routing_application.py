from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.contracts import CommandOutput, ExecutionContext
from app.application.executor import CommandExecutor
from app.application.handlers.street_routing import StreetRoutingHandler
from app.application.handlers.transit_routing import TransitRoutingHandler
from app.integrations.openrouteservice import (
    OpenRouteServiceInvalidResponseError,
    OpenRouteServiceResponseError,
)
from app.integrations.transitous import (
    TransitousInvalidResponseError,
    TransitousResponseError,
)
from app.schemas.routing import (
    StreetRouteProfile,
    StreetRouteRequest,
    TransitMode,
    TransitRouteRequest,
)
from app.services.street_routing_service import PROFILE_MAP, StreetRoutingService
from app.services.transit_routing_service import (
    PROVIDER_MODE_NAMES,
    TransitRoutingService,
    normalize_provider_mode,
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
    assert route["legs"][0]["mode"] == "walking"
    assert route["legs"][1]["mode"] == "subway"
    assert route["legs"][1]["route_short_name"] == "U2"
    assert route["legs"][1]["headsign"] == "Ruhleben"
    assert route["legs"][1]["scheduled_departure_time"].endswith("+02:00")
    tracked = service.upstream_call_repo.create.await_args.kwargs
    assert tracked["success"] is True
    assert tracked["provider"] == "transitous"
    assert tracked["url_path"] == "/api/v6/plan"
    sent_params = client.get.await_args.args[1]
    assert sent_params["transitModes"] == ["TRANSIT"]
    assert sent_params["preTransitModes"] == "WALK"
    assert sent_params["postTransitModes"] == "WALK"
    assert sent_params["directModes"] == ""
    assert sent_params["maxPreTransitTime"] == 900
    assert sent_params["maxPostTransitTime"] == 900
    assert tracked["request_payload"]["max_pre_transit_time"] == 900
    assert tracked["request_payload"]["max_post_transit_time"] == 900


@pytest.mark.asyncio
async def test_transit_service_preserves_explicit_transit_mode():
    client = SimpleNamespace(get=AsyncMock(return_value={"itineraries": []}))
    service = TransitRoutingService(SimpleNamespace(), client=client)
    service.upstream_call_repo = SimpleNamespace(create=AsyncMock())

    result = await service.plan_route(
        job_id=uuid4(),
        request=transit_request(transit_modes=[TransitMode.TRANSIT]),
    )

    expected = ["TRANSIT"]
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
        ["TRANSIT"],
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


def test_all_documented_provider_leg_modes_are_normalized():
    assert PROVIDER_MODE_NAMES == {
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
    for provider_mode, public_mode in PROVIDER_MODE_NAMES.items():
        assert normalize_provider_mode(provider_mode) == (public_mode, [])


@pytest.mark.parametrize(
    "provider_mode",
    ["DEBUG_BUS_ROUTE", "DEBUG_RAILWAY_ROUTE", "DEBUG_FERRY_ROUTE"],
)
def test_debug_provider_modes_are_lowercased_with_warning(provider_mode):
    mode, warnings = normalize_provider_mode(provider_mode)

    assert mode == provider_mode.lower()
    assert warnings == [
        {
            "type": "provider_debug_mode",
            "provider_mode": provider_mode,
            "normalized_mode": provider_mode.lower(),
        }
    ]


def test_bicycle_is_not_treated_as_a_provider_leg_mode():
    assert "BICYCLE" not in PROVIDER_MODE_NAMES
    assert normalize_provider_mode("BICYCLE") == (
        "bicycle",
        [
            {
                "type": "unknown_provider_mode",
                "provider_mode": "BICYCLE",
                "normalized_mode": "bicycle",
            }
        ],
    )


def test_provider_mode_warnings_are_exposed_on_route_and_result():
    result = TransitRoutingService._normalize(
        {
            "itineraries": [
                {
                    "legs": [
                        {"mode": "DEBUG_BUS_ROUTE"},
                        {"mode": "NEW_PROVIDER_MODE"},
                    ]
                }
            ]
        },
        transit_request(),
        ["TRANSIT"],
    )

    route = result["routes"][0]
    assert [leg["mode"] for leg in route["legs"]] == [
        "debug_bus_route",
        "new_provider_mode",
    ]
    assert [warning["type"] for warning in route["warnings"]] == [
        "provider_debug_mode",
        "unknown_provider_mode",
    ]
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


def test_street_profiles_map_to_the_documented_ors_profiles():
    assert PROFILE_MAP == {
        StreetRouteProfile.WALKING: "foot-walking",
        StreetRouteProfile.CYCLING: "cycling-regular",
        StreetRouteProfile.DRIVING: "driving-car",
    }


def test_street_service_keeps_other_provider_error_codes_as_errors():
    with pytest.raises(OpenRouteServiceInvalidResponseError):
        StreetRoutingService._normalize(
            {"error": {"code": 2010, "message": "invalid request"}},
            street_request(),
        )


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


@pytest.mark.asyncio
async def test_full_routing_result_is_persisted_before_mcp_compaction():
    job = SimpleNamespace(id=uuid4(), command="routing.street.plan")
    full_route = {
        "geometry": "encoded-polyline",
        "segments": [{"instruction": "x" * 140_000}],
    }
    output = CommandOutput(
        status="ok",
        result_type="routing.street.plan",
        items=[full_route],
        meta={"provider": "openrouteservice", "returned": 1},
        result_payload={
            "status": "ok",
            "provider": "openrouteservice",
            "returned": 1,
            "routes": [full_route],
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

    await executor.run_payload(
        job_id=job.id,
        command=job.command,
        payload={},
        source="test",
    )

    executor.result_repo.create.assert_awaited_once_with(
        job_id=job.id,
        result_type="routing.street.plan",
        items=[full_route],
        meta={"provider": "openrouteservice", "returned": 1},
    )
    executor.job_repo.mark_succeeded.assert_awaited_once_with(
        job,
        result_payload=output.result_payload,
    )

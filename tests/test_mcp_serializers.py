import json
from copy import deepcopy
from datetime import datetime, timezone

from app.application.contracts import CommandOutput
from app.mcp.serializers.common import (
    SEARCH_RESPONSE_LIMIT_BYTES,
    iso_timestamp,
    json_size,
)
from app.mcp.serializers.events import serialize_events
from app.mcp.serializers.movie_showings import serialize_movie_showings
from app.mcp.serializers.movies import serialize_movies
from app.mcp.serializers.places import serialize_places
from app.mcp.schemas.routing import (
    PlanPublicTransportInput,
    PlanStreetRouteInput,
    PublicTransportMode,
    RoutePoint,
    StreetTravelMode,
)
from app.mcp.serializers.routing import (
    serialize_public_transport,
    serialize_street_route,
)


def output(payload):
    items = payload.get("items", payload.get("routes", []))
    return CommandOutput(
        status=payload.get("status", "ok"),
        result_type="test",
        items=items,
        meta={},
        result_payload=payload,
    )


def test_event_serializer_keeps_only_matching_dates_without_mutating_full_result():
    payload = {
        "status": "ok",
        "count": 2,
        "returned": 2,
        "filters": {
            "actual_since": 1_799_999_000,
            "categories": "concert",
        },
        "geo": {"status": "ok", "kind": "kudago_location"},
        "items": [
            {
                "id": 1,
                "title": "Event",
                "body_text": "large",
                "images": [{"image": "x"}],
                "dates": [
                    {"start": 1_700_000_000, "end": 1_700_000_100},
                    {"start": 1_800_000_000, "end": 1_800_000_100},
                ],
            },
            {
                "id": 2,
                "title": "Historical only",
                "dates": [{"start": 1_700_000_000, "end": 1_700_000_100}],
            },
        ],
    }
    original = deepcopy(payload)

    data = serialize_events(
        output(payload),
        actual_since=1_799_999_000,
        actual_until=1_800_001_000,
        applied_timezone="Europe/Moscow",
        applied_filters={"date": "2027-01-15", "categories": ["concert"]},
    )

    assert len(data["items"]) == 1
    assert len(data["items"][0]["matching_dates"]) == 1
    assert data["returned"] == 1
    assert data["applied_timezone"] == "Europe/Moscow"
    assert data["applied_filters"] == {
        "date": "2027-01-15",
        "categories": ["concert"],
    }
    assert "actual_since" not in data["applied_filters"]
    assert "geo" not in data
    assert "body_text" not in data["items"][0]
    assert "images" not in data["items"][0]
    assert payload == original


def test_event_serializer_drops_thousands_of_historical_dates_and_stays_small():
    historical_dates = [
        {"start": 1_700_000_000 + index, "end": 1_700_000_001 + index}
        for index in range(5_000)
    ]
    payload = {
        "status": "ok",
        "count": 1,
        "returned": 1,
        "items": [
            {
                "id": 1,
                "title": "Event",
                "dates": historical_dates
                + [{"start": 1_800_000_000, "end": 1_800_000_100}],
            }
        ],
    }
    original_date_count = len(payload["items"][0]["dates"])

    data = serialize_events(
        output(payload),
        actual_since=1_799_999_000,
        actual_until=1_800_001_000,
        applied_timezone="+03:00",
    )

    assert len(data["items"][0]["matching_dates"]) == 1
    assert len(payload["items"][0]["dates"]) == original_date_count
    assert json_size(data) <= SEARCH_RESPONSE_LIMIT_BYTES


def test_event_serializer_preserves_unbounded_dates_and_compact_schedules():
    actual_since = 1_800_000_000
    actual_until = 1_800_001_000
    payload = {
        "status": "ok",
        "count": 1,
        "returned": 1,
        "items": [
            {
                "id": 1,
                "title": "Long-running event",
                "dates": [
                    {
                        "start": -62_135_433_000,
                        "end": 253_370_754_000,
                        "is_startless": True,
                        "is_endless": True,
                        "is_continuous": True,
                        "schedules": [
                            {
                                "days_of_week": [1, 2, 3, 4, 5, 6],
                                "start_time": "10:00:00",
                                "end_time": "18:00:00",
                                "unexpected_field": "must not be exposed",
                            },
                            "not-an-object",
                            {},
                        ],
                        "use_place_schedule": False,
                    },
                    {
                        "start": -62_135_433_000,
                        "end": actual_until,
                        "is_startless": True,
                    },
                    {
                        "start": actual_since,
                        "end": 253_370_754_000,
                        "is_endless": True,
                        "use_place_schedule": True,
                    },
                    {
                        "end": actual_since - 1,
                        "is_startless": True,
                    },
                    {
                        "start": actual_until + 1,
                        "is_endless": True,
                    },
                ],
            }
        ],
    }
    original = deepcopy(payload)

    data = serialize_events(
        output(payload),
        actual_since=actual_since,
        actual_until=actual_until,
        applied_timezone="Europe/Moscow",
    )

    matching_dates = data["items"][0]["matching_dates"]
    assert len(matching_dates) == 3
    assert matching_dates[0] == {
        "start": None,
        "end": None,
        "is_startless": True,
        "is_endless": True,
        "is_continuous": True,
        "use_place_schedule": False,
        "schedules": [
            {
                "days_of_week": [1, 2, 3, 4, 5, 6],
                "start_time": "10:00:00",
                "end_time": "18:00:00",
            }
        ],
    }
    assert matching_dates[1]["start"] is None
    assert matching_dates[1]["end"] == iso_timestamp(actual_until)
    assert matching_dates[2]["start"] == iso_timestamp(actual_since)
    assert matching_dates[2]["end"] is None
    assert matching_dates[2]["use_place_schedule"] is True
    assert matching_dates[2]["schedules"] == []
    assert json_size(data) <= SEARCH_RESPONSE_LIMIT_BYTES
    json.dumps(data, ensure_ascii=False)
    assert payload == original


def test_iso_timestamp_never_raises_for_invalid_external_values():
    assert iso_timestamp(10**100) is None
    assert iso_timestamp("not-a-timestamp") is None
    assert iso_timestamp(None) is None
    assert iso_timestamp(True) is None


def test_event_schedules_do_not_break_the_search_response_limit():
    schedules = [
        {
            "days_of_week": [1, 2, 3, 4, 5, 6, 7],
            "start_time": "10:00:00",
            "end_time": "18:00:00",
        }
        for _ in range(2_000)
    ]
    payload = {
        "status": "ok",
        "count": 1,
        "returned": 1,
        "items": [
            {
                "id": 1,
                "title": "Large schedule",
                "dates": [
                    {
                        "start": -62_135_433_000,
                        "end": 253_370_754_000,
                        "is_startless": True,
                        "is_endless": True,
                        "schedules": schedules,
                    }
                ],
            }
        ],
    }

    data = serialize_events(
        output(payload),
        actual_since=1_800_000_000,
        actual_until=1_800_001_000,
        applied_timezone="Europe/Moscow",
    )

    assert json_size(data) <= SEARCH_RESPONSE_LIMIT_BYTES
    assert data["truncated"] is True
    assert len(payload["items"][0]["dates"][0]["schedules"]) == 2_000


def test_semantic_flags_distinguish_places_movies_and_showings():
    base = {"status": "ok", "count": 0, "returned": 0, "items": []}
    assert serialize_places(output(base))["schedule_verified"] is False
    assert serialize_movies(output(base))["showing_times_verified"] is False
    assert serialize_movie_showings(output(base))["schedule_verified"] is True


def test_movie_showings_exposes_the_default_next_seven_day_window():
    payload = {
        "status": "ok",
        "count": 0,
        "returned": 0,
        "items": [],
        "filters": {
            "actual_since": 1_800_000_000,
            "actual_until": 1_800_604_800,
        },
    }

    data = serialize_movie_showings(
        output(payload),
        default_window_applied=True,
    )

    assert data["applied_time_window"]["source"] == "default_next_7_days"
    assert "actual_since" not in data.get("applied_filters", {})


def test_street_route_serializer_preserves_labels_and_removes_geometry():
    payload = {
        "status": "ok",
        "provider": "openrouteservice",
        "profile": "walking",
        "query": {
            "origin": {"lat": 55.75, "lon": 37.61},
            "destination": {"lat": 55.76, "lon": 37.62},
        },
        "routes": [{"geometry": "encoded", "segments": []}],
        "returned": 1,
        "warnings": [],
        "attribution": [],
    }
    request = PlanStreetRouteInput(
        origin=RoutePoint(
            latitude=55.75,
            longitude=37.61,
            label="Origin",
        ),
        destination=RoutePoint(
            latitude=55.76,
            longitude=37.62,
            label="Destination",
        ),
        travel_mode=StreetTravelMode.WALKING,
    )
    data = serialize_street_route(output(payload), agent_request=request)

    assert data["result_kind"] == "street_route"
    assert data["result_status"] == "ok"
    assert data["route_verified"] is True
    assert "geometry" not in data["routes"][0]
    assert data["routes"][0]["geometry_hidden"] is True
    assert data["request"]["origin"] == {
        "latitude": 55.75,
        "longitude": 37.61,
        "label": "Origin",
    }
    assert data["request"]["travel_mode"] == "walking"
    assert "profile" not in data
    assert "query" not in data

    no_route = serialize_street_route(
        output({"status": "no_route", "routes": [], "returned": 0}),
        agent_request=request,
    )
    assert no_route["result_status"] == "no_route"
    assert no_route["route_verified"] is False
    assert no_route["routes"] == []


def test_public_transport_serializer_uses_original_agent_request():
    payload = {
        "status": "ok",
        "provider": "transitous",
        "query": {
            "origin": {"lat": 55.75, "lon": 37.61},
            "destination": {"lat": 55.76, "lon": 37.62},
            "time": "2026-07-13T12:00:00+03:00",
            "arrive_by": True,
            "transit_modes": ["SUBWAY", "HIGHSPEED_RAIL"],
        },
        "routes": [{"legs": []}],
        "returned": 1,
    }

    request = PlanPublicTransportInput(
        origin=RoutePoint(
            latitude=55.75,
            longitude=37.61,
            label="Origin",
        ),
        destination=RoutePoint(
            latitude=55.76,
            longitude=37.62,
            label="Destination",
        ),
        arrival_time=datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc),
        transport_modes=[
            PublicTransportMode.SUBWAY,
            PublicTransportMode.HIGH_SPEED_RAIL,
        ],
        max_transfers=2,
        max_routes=2,
    )
    data = serialize_public_transport(output(payload), agent_request=request)

    assert data["result_kind"] == "public_transport_routes"
    assert data["result_status"] == "ok"
    assert data["request"] == {
        "origin": {
            "latitude": 55.75,
            "longitude": 37.61,
            "label": "Origin",
        },
        "destination": {
            "latitude": 55.76,
            "longitude": 37.62,
            "label": "Destination",
        },
        "time_constraint": {
            "type": "arrival_time",
            "value": "2026-07-13T12:00:00+00:00",
        },
        "transport_mode_policy": "restricted",
        "transport_modes": ["subway", "high_speed_rail"],
        "max_transfers": 2,
        "max_routes": 2,
        "access_mode": "walking",
        "egress_mode": "walking",
        "max_access_seconds": 900,
        "max_egress_seconds": 900,
        "direct_routes_enabled": False,
    }
    assert "query" not in data


def test_public_transport_no_route_has_cautious_conditional_diagnostics():
    payload = {
        "status": "no_route",
        "provider": "transitous",
        "routes": [],
        "returned": 0,
    }
    unrestricted = PlanPublicTransportInput(
        origin=RoutePoint(latitude=55.75, longitude=37.61),
        destination=RoutePoint(latitude=55.76, longitude=37.62),
        departure_time=datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc),
    )
    restricted = unrestricted.model_copy(
        update={"transport_modes": [PublicTransportMode.SUBURBAN_RAIL]}
    )

    data = serialize_public_transport(output(payload), agent_request=unrestricted)
    restricted_data = serialize_public_transport(
        output(payload),
        agent_request=restricted,
    )

    assert data["result_status"] == "no_route"
    assert data["route_verified"] is False
    assert data["diagnostic"] == {
        "code": "provider_returned_no_itineraries",
        "coverage_status": "unknown",
        "message": (
            "The provider returned no itinerary for the exact requested points, "
            "time and restrictions."
        ),
    }
    assert data["request"]["transport_mode_policy"] == "all_provider_supported"
    assert data["request"]["transport_modes"] is None
    assert "remove_mode_restrictions" not in data["retry_hints"]
    assert restricted_data["retry_hints"][-1] == "remove_mode_restrictions"

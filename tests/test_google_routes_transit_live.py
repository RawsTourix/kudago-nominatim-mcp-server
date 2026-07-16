from __future__ import annotations

import inspect
import json

import pytest

import scripts.test_google_routes_transit_live as google_live
from scripts.test_google_routes_transit_live import (
    DEFAULT_BASE_URL,
    GOOGLE_TRANSIT_FIELD_MASK,
    RAW_RESPONSE_STORAGE_ENABLED,
    build_headers,
    build_live_plan,
    build_request_body,
    compare_repeat_results,
    local_time_to_utc_z,
    parse_response,
    prepare_request,
    sanitize_exception,
    sanitize_text,
    sanitize_value,
)


API_KEY = "unit-test-secret-key"


def _case(name: str = "nakhabino_kurskaya__baseline"):
    return next(case for case in build_live_plan(local_today=google_live.date(2026, 7, 16)) if case.name == name)


def _payload(*, include_fare: bool = True, include_transit: bool = True):
    transit_step = {
        "distanceMeters": 21000,
        "staticDuration": "1200s",
        "travelMode": "TRANSIT",
        "transitDetails": {
            "stopDetails": {
                "departureStop": {
                    "name": "Nakhabino",
                    "location": {
                        "latLng": {"latitude": 55.8415, "longitude": 37.1849}
                    },
                },
                "departureTime": "2026-07-17T15:05:00Z",
                "arrivalStop": {
                    "name": "Kurskaya",
                    "location": {
                        "latLng": {"latitude": 55.7588, "longitude": 37.6580}
                    },
                },
                "arrivalTime": "2026-07-17T15:25:00Z",
            },
            "headsign": "Podolsk",
            "stopCount": 12,
            "transitLine": {
                "agencies": [{"name": "Moscow Metro"}],
                "name": "MCD-2",
                "nameShort": "D2",
                "vehicle": {
                    "name": {"text": "Commuter train"},
                    "type": "COMMUTER_TRAIN",
                },
            },
        },
    }
    steps = [
        {
            "distanceMeters": 100,
            "staticDuration": "300s",
            "travelMode": "WALK",
        },
        *([transit_step] if include_transit else []),
        {
            "distanceMeters": 100,
            "staticDuration": "300s",
            "travelMode": "WALK",
        },
    ]
    localized_values = {
        "distance": {"text": "22 km"},
        "duration": {"text": "30 min"},
    }
    if include_fare:
        localized_values["transitFare"] = {"text": "100 RUB"}
    return {
        "routes": [
            {
                "distanceMeters": 22000,
                "duration": "1800s",
                "routeLabels": ["DEFAULT_ROUTE"],
                "legs": [
                    {
                        "distanceMeters": 22000,
                        "duration": "1800s",
                        "steps": steps,
                    }
                ],
                "localizedValues": localized_values,
            }
        ]
    }


def _parsed(payload=None, *, status: int = 200, case_name: str = "nakhabino_kurskaya__baseline"):
    return parse_response(
        case=_case(case_name),
        http_status=status,
        payload=_payload() if payload is None else payload,
        elapsed_ms=12.3,
        response_size_bytes=456,
    )


def test_01_base_url_is_used_without_appending_a_slash():
    prepared = prepare_request(_case(), base_url=DEFAULT_BASE_URL, api_key=API_KEY)

    assert prepared.url == DEFAULT_BASE_URL
    assert not prepared.url.endswith("/")


def test_02_api_key_is_sent_only_in_the_google_api_key_header():
    prepared = prepare_request(_case(), base_url=DEFAULT_BASE_URL, api_key=API_KEY)

    matching_values = [name for name, value in prepared.headers.items() if value == API_KEY]
    assert matching_values == ["X-Goog-Api-Key"]


def test_03_api_key_is_absent_from_url_and_body():
    prepared = prepare_request(_case(), base_url=DEFAULT_BASE_URL, api_key=API_KEY)

    assert API_KEY not in prepared.url
    assert API_KEY not in json.dumps(prepared.body)


def test_04_field_mask_is_mandatory():
    with pytest.raises(ValueError, match="FieldMask"):
        build_headers(API_KEY, "")


def test_05_field_mask_has_no_wildcard_or_polyline():
    paths = GOOGLE_TRANSIT_FIELD_MASK.split(",")

    assert "routes.*" not in paths
    assert all("polyline" not in path.casefold() for path in paths)


def test_06_origin_and_destination_keep_latitude_longitude_order():
    case = _case()
    body = build_request_body(case)

    assert body["origin"]["location"]["latLng"] == {
        "latitude": case.scenario.origin.latitude,
        "longitude": case.scenario.origin.longitude,
    }
    assert body["destination"]["location"]["latLng"] == {
        "latitude": case.scenario.destination.latitude,
        "longitude": case.scenario.destination.longitude,
    }


def test_07_travel_mode_is_transit():
    assert build_request_body(_case())["travelMode"] == "TRANSIT"


def test_08_every_request_has_exactly_one_temporal_constraint():
    for case in build_live_plan(local_today=google_live.date(2026, 7, 16)):
        body = build_request_body(case)
        assert sum(field in body for field in ("departureTime", "arrivalTime")) == 1


def test_09_local_time_is_converted_with_zoneinfo_to_utc_z():
    assert local_time_to_utc_z(
        google_live.date(2026, 7, 17), 18, "Europe/Berlin"
    ) == "2026-07-17T16:00:00Z"
    assert local_time_to_utc_z(
        google_live.date(2026, 7, 17), 18, "America/New_York"
    ) == "2026-07-17T22:00:00Z"


def test_10_main_matrix_contains_seven_baseline_scenarios():
    plan = build_live_plan(local_today=google_live.date(2026, 7, 16))

    assert len([case for case in plan if case.variant == "baseline"]) == 7


def test_11_full_live_plan_contains_exactly_twelve_requests():
    plan = build_live_plan(local_today=google_live.date(2026, 7, 16))

    assert len(plan) == 12
    assert [case.variant for case in plan].count("arrive_by") == 2
    assert [case.variant for case in plan].count("preferences") == 1
    assert [case.variant for case in plan].count("repeat") == 2


def test_12_parser_extracts_transit_stop_details():
    route = _parsed()["routes"][0]
    step = route["transit_steps"][0]

    assert step["departure_stop"] == {
        "name": "Nakhabino",
        "latitude": 55.8415,
        "longitude": 37.1849,
    }
    assert step["arrival_stop"]["name"] == "Kurskaya"


def test_13_parser_extracts_transit_line_and_vehicle():
    step = _parsed()["routes"][0]["transit_steps"][0]

    assert step["line_name"] == "MCD-2"
    assert step["line_short_name"] == "D2"
    assert step["vehicle_type"] == "COMMUTER_TRAIN"
    assert step["vehicle_name"] == "Commuter train"
    assert step["agencies"] == ["Moscow Metro"]


def test_14_parser_extracts_and_localizes_transit_timestamps():
    route = _parsed()["routes"][0]
    step = route["transit_steps"][0]

    assert route["departure_time"] == "2026-07-17T15:05:00Z"
    assert route["arrival_time"] == "2026-07-17T15:25:00Z"
    assert step["departure_time_local"] == "2026-07-17T18:05:00+03:00"
    assert route["time_validation"]["valid"] is True


def test_15_fare_is_optional():
    result = _parsed(_payload(include_fare=False))

    assert result["routes"][0]["fare"] is None
    assert result["classification"] == "verified_timetable_route"


def test_16_empty_or_omitted_routes_are_classified_as_no_route():
    empty = _parsed({"routes": []})
    omitted = _parsed({})

    assert empty["classification"] == "no_route"
    assert omitted["classification"] == "no_route"
    assert empty["route_count"] == omitted["route_count"] == 0


def test_17_api_error_is_classified_as_provider_error():
    result = _parsed(
        {
            "error": {
                "code": 403,
                "status": "PERMISSION_DENIED",
                "message": "API access denied",
            }
        },
        status=403,
    )

    assert result["classification"] == "provider_error"
    assert result["provider_error"]["provider_status"] == "PERMISSION_DENIED"


def test_18_duration_without_transit_details_is_not_a_schedule():
    result = _parsed(_payload(include_transit=False))

    assert result["routes"][0]["duration_seconds"] == 1800
    assert result["classification"] == "route_without_transit_details"


def test_19_allowed_travel_modes_are_marked_as_preferences_not_strict_filters():
    case = _case("nakhabino_kurskaya__fewer_transfers")
    body = build_request_body(case)

    assert case.preference_semantics == "preference_not_strict_filter"
    assert body["transitPreferences"] == {
        "allowedTravelModes": ["TRAIN", "SUBWAY", "RAIL"],
        "routingPreference": "FEWER_TRANSFERS",
    }


def test_20_sanitizer_removes_key_header_name_value_and_exception_text():
    raw = f"X-Goog-Api-Key: {API_KEY}"
    sanitized = sanitize_text(raw, API_KEY)
    mapping = sanitize_value({"x-goog-api-key": API_KEY, "message": raw}, API_KEY)
    exception = sanitize_exception(RuntimeError(raw), API_KEY)

    for value in (sanitized, json.dumps(mapping), json.dumps(exception)):
        assert API_KEY not in value
        assert "x-goog-api-key" not in value.casefold()


def test_21_repeat_comparison_ignores_technical_metadata():
    first = _parsed()
    second = _parsed(case_name="nakhabino_kurskaya__repeat")
    second["elapsed_ms"] = 999.9
    second["response_size_bytes"] = 9999
    second["request_attempts"] = 2
    second["retry_count"] = 1

    assert compare_repeat_results(first, second) is True


def test_22_raw_response_and_api_key_are_never_written_to_disk():
    source = inspect.getsource(google_live)

    assert RAW_RESPONSE_STORAGE_ENABLED is False
    assert ".write_text(" not in source
    assert ".write_bytes(" not in source
    assert "response.request" not in source
    assert "curl " not in source.casefold()

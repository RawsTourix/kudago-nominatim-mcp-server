from scripts.test_geoapify_transit_live import (
    REDACTED,
    ROUTING_MODES,
    SCENARIOS,
    Point,
    build_main_matrix,
    build_request_params,
    compact_raw_payload,
    compare_repeat_payloads,
    format_waypoints,
    normalize_base_url,
    parse_response,
    sanitize_text,
    sanitize_value,
)


def _request() -> dict[str, str]:
    return {
        "waypoints": "1.0,2.0|3.0,4.0",
        "mode": "transit",
        "format": "json",
        "lang": "en",
        "apiKey": REDACTED,
    }


def _parse(payload, *, mode="transit", status=200, provider_error=None):
    return parse_response(
        scenario="test",
        mode=mode,
        http_status=status,
        elapsed_ms=12.0,
        response_size_bytes=100,
        payload=payload,
        request=_request(),
        provider_error=provider_error,
    )


def _route_payload(**route_overrides):
    route = {
        "distance": 1200,
        "time": 600,
        "geometry": [[1.0, 2.0], [3.0, 4.0]],
        "legs": [
            {
                "steps": [
                    {
                        "mode": "transit",
                        "instruction": {"type": "TransitTransfer"},
                        "route_name": "M2",
                        "stop_name": "Central",
                    }
                ]
            }
        ],
        **route_overrides,
    }
    return {"properties": {"mode": "transit"}, "results": [route]}


def test_waypoints_use_latitude_longitude_order():
    origin = Point("origin", 55.1, 37.2)
    destination = Point("destination", 52.3, 13.4)

    assert format_waypoints(origin, destination) == "55.1,37.2|52.3,13.4"


def test_base_url_removes_trailing_slashes():
    assert normalize_base_url("https://api.geoapify.com/v1/routing///") == (
        "https://api.geoapify.com/v1/routing"
    )


def test_exactly_two_supported_modes_and_fourteen_main_requests():
    assert ROUTING_MODES == ("transit", "approximated_transit")
    matrix = build_main_matrix("secret")
    assert len(SCENARIOS) == 7
    assert len(matrix) == 14
    assert {mode for _, mode, _ in matrix} == set(ROUTING_MODES)
    assert all(
        {"departure_time", "arrival_time", "date", "time"}.isdisjoint(params)
        for _, _, params in matrix
    )


def test_request_params_include_json_format_and_redactable_key():
    params = build_request_params(SCENARIOS[0], "transit", "top-secret")

    assert params["format"] == "json"
    assert params["apiKey"] == "top-secret"
    assert params["waypoints"].startswith("55.8415879,37.184911")


def test_sanitizer_removes_key_from_query_string():
    value = "failed: https://example.test/route?apiKey=secret-value&mode=transit"

    sanitized = sanitize_text(value, "secret-value")

    assert "secret-value" not in sanitized
    assert f"apiKey={REDACTED}" in sanitized


def test_sanitizer_removes_exact_key_and_nested_api_key_fields():
    value = {
        "apiKey": "exact-secret",
        "message": "rejected exact-secret",
        "nested": ["apikey=exact-secret&mode=transit"],
    }

    sanitized = sanitize_value(value, "exact-secret")

    assert "exact-secret" not in str(sanitized)
    assert sanitized["apiKey"] == REDACTED


def test_parser_handles_properties_results_and_does_not_treat_time_as_schedule():
    summary = _parse(_route_payload())

    assert summary["result_count"] == 1
    assert summary["distance_meters"] == 1200
    assert summary["duration_seconds"] == 600
    assert summary["leg_count"] == 1
    assert summary["step_count"] == 1
    assert summary["classification"] == "structured_transit_route_without_schedule"
    assert summary["has_departure_timestamps"] is False
    assert summary["has_arrival_timestamps"] is False
    assert summary["has_service_dates"] is False


def test_parser_handles_empty_results():
    summary = _parse({"properties": {}, "results": []})

    assert summary["result_count"] == 0
    assert summary["classification"] == "no_route"


def test_parser_handles_http_and_structured_provider_errors():
    http_error = _parse(
        {"error": "unauthorized"},
        status=401,
        provider_error={"type": "http_error", "status": 401},
    )
    structured_error = _parse(
        {"statusCode": 400, "error": "Bad Request", "message": "invalid"}
    )

    assert http_error["classification"] == "provider_error"
    assert structured_error["classification"] == "provider_error"


def test_parser_rejects_http_200_with_unexpected_shape():
    summary = _parse({"features": []})

    assert summary["classification"] == "invalid_response"
    assert summary["invalid_response"] is True


def test_recursive_field_search_detects_timetable_and_realtime_evidence():
    payload = _route_payload(
        legs=[
            {
                "steps": [
                    {
                        "instruction": {"type": "Transit"},
                        "departure_time": "2026-07-17T10:00:00+03:00",
                        "arrival_time": "2026-07-17T10:20:00+03:00",
                        "service_date": "2026-07-17",
                        "realtime": False,
                        "delay": 0,
                        "route_short_name": "D2",
                        "stop_name": "Nakhabino",
                    }
                ]
            }
        ]
    )

    summary = _parse(payload)

    assert summary["has_departure_timestamps"] is True
    assert summary["has_arrival_timestamps"] is True
    assert summary["has_service_dates"] is True
    assert summary["has_realtime_flags"] is True
    assert summary["classification"] == "verified_timetable_route"
    assert summary["mcd2_recognized"] is True


def test_geometry_is_replaced_in_raw_output_and_absent_from_compact_report():
    payload = _route_payload()
    compact_raw = compact_raw_payload(payload, "secret")
    summary = _parse(payload)

    raw_geometry = compact_raw["results"][0]["geometry"]
    assert raw_geometry == {
        "redacted": True,
        "type": "list",
        "coordinate_count": 2,
    }
    assert "geometry" not in summary
    assert summary["has_route_geometry"] is True


def test_approximated_transit_is_never_classified_as_verified_timetable():
    payload = _route_payload(
        legs=[
            {
                "steps": [
                    {
                        "instruction": {"type": "Transit"},
                        "departure_time": "2026-07-17T10:00:00+03:00",
                        "arrival_time": "2026-07-17T10:20:00+03:00",
                        "service_date": "2026-07-17",
                        "route_name": "D2",
                    }
                ]
            }
        ]
    )

    summary = _parse(payload, mode="approximated_transit")

    assert summary["classification"] == "approximated_network_route"


def test_repeat_comparison_ignores_geometry_and_technical_metadata():
    first = _route_payload()
    first["metadata"] = {"request_id": "one"}
    second = _route_payload(geometry=[[9.0, 8.0], [7.0, 6.0]])
    second["metadata"] = {"request_id": "two"}

    assert compare_repeat_payloads(first, second) is True

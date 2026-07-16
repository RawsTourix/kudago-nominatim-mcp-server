from datetime import date

import pytest

from scripts.test_transitous_coverage_live import (
    MAX_PROVIDER_API_REQUESTS,
    POINTS,
    bbox_around,
    build_plan_scenarios,
    classify_diagnostics,
    normalize_stops,
    plan_params,
)


def test_diagnostic_matrix_is_bounded_and_covers_requested_variants():
    nearest_stop_ids = {key: f"stop-{key}" for key in POINTS}
    scenarios = build_plan_scenarios(date(2026, 7, 17), nearest_stop_ids)
    names = {scenario.name for scenario in scenarios}

    assert len(scenarios) == 17
    assert len(POINTS) + len(POINTS) + len(scenarios) == MAX_PROVIDER_API_REQUESTS
    assert {
        "berlin_coordinate_12",
        "berlin_stop_ids_12",
        "moscow_center_to_kurskaya_12",
        "nakhabino_kurskaya_08_transit",
        "nakhabino_kurskaya_12_transit",
        "nakhabino_kurskaya_18_transit",
        "nakhabino_kurskaya_12_explicit_modes",
        "nakhabino_kurskaya_12_access_1800",
        "nakhabino_kurskaya_12_radius_500",
        "nakhabino_kurskaya_12_radius_1000",
        "nakhabino_kurskaya_stop_ids_12",
        "nakhabino_arkhangelskoye_08_transit",
        "nakhabino_arkhangelskoye_12_transit",
        "nakhabino_arkhangelskoye_18_transit",
        "nakhabino_arkhangelskoye_12_access_1800",
        "nakhabino_arkhangelskoye_12_radius_1000",
        "nakhabino_arkhangelskoye_stop_ids_12",
    } == names

    explicit = next(
        scenario
        for scenario in scenarios
        if scenario.name == "nakhabino_kurskaya_12_explicit_modes"
    )
    assert explicit.transit_modes == ("SUBURBAN", "SUBWAY", "BUS")
    radius = next(
        scenario
        for scenario in scenarios
        if scenario.name == "nakhabino_kurskaya_12_radius_500"
    )
    params = plan_params(radius, date(2026, 7, 17))
    assert params["radius"] == 500
    assert params["maxPreTransitTime"] == 900
    assert params["maxPostTransitTime"] == 900
    assert params["directModes"] == ()


def test_diagnostic_matrix_skips_stop_routes_when_stops_are_missing():
    scenarios = build_plan_scenarios(date(2026, 7, 17), {})

    assert len(scenarios) == 14
    assert all(scenario.endpoint_representation == "coordinate" for scenario in scenarios)


def test_map_bbox_and_stop_normalization_keep_distance_and_modes():
    point = POINTS["nakhabino"]
    bbox = bbox_around(point)
    stops = normalize_stops(
        [
            {
                "stopId": "ru-stop",
                "name": "Nakhabino",
                "lat": point.latitude,
                "lon": point.longitude,
                "modes": ["SUBURBAN", "BUS"],
            }
        ],
        point,
    )

    assert bbox["grouped"] == "false"
    assert bbox["min"] != bbox["max"]
    assert stops == [
        {
            "stop_id": "ru-stop",
            "name": "Nakhabino",
            "latitude": point.latitude,
            "longitude": point.longitude,
            "modes": ["SUBURBAN", "BUS"],
            "distance_metres": 0.0,
        }
    ]


def _areas(*, stops: int, stoptimes: int) -> dict[str, dict[str, int]]:
    return {
        key: {"stops_count": stops, "stoptimes_count": stoptimes}
        for key in ("nakhabino", "kurskaya", "moscow_center", "arkhangelskoye")
    }


def _plans(**routes: int) -> list[dict[str, object]]:
    baseline = {"berlin_coordinate_12": 1, **routes}
    return [
        {
            "name": name,
            "family": "berlin" if name.startswith("berlin") else "russia",
            "itineraries_count": count,
        }
        for name, count in baseline.items()
    ]


@pytest.mark.parametrize(
    ("areas", "plans", "expected"),
    [
        (_areas(stops=1, stoptimes=1), _plans(berlin_coordinate_12=0), "integration_bug"),
        (_areas(stops=0, stoptimes=0), _plans(), "provider_coverage_unavailable"),
        (
            _areas(stops=1, stoptimes=1),
            _plans(nakhabino_kurskaya_12_access_1800=1),
            "access_policy_issue",
        ),
        (
            _areas(stops=1, stoptimes=1),
            _plans(nakhabino_kurskaya_12_radius_500=1),
            "coordinate_matching_issue",
        ),
        (
            _areas(stops=1, stoptimes=1),
            _plans(nakhabino_kurskaya_stop_ids_12=1),
            "coordinate_matching_issue",
        ),
        (_areas(stops=1, stoptimes=0), _plans(), "provider_coverage_partial"),
        (_areas(stops=1, stoptimes=1), _plans(), "inconclusive"),
    ],
)
def test_diagnostic_classification(areas, plans, expected):
    assert classify_diagnostics(areas, plans) == expected

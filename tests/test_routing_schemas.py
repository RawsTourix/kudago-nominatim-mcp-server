from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas.routing import (
    StreetRouteProfile,
    StreetRouteRequest,
    TransitMode,
    TransitRouteRequest,
)


def transit_payload(**overrides):
    payload = {
        "origin_lat": 55.842,
        "origin_lon": 37.180,
        "destination_lat": 55.751,
        "destination_lon": 37.617,
    }
    payload.update(overrides)
    return payload


def test_routing_schemas_accept_valid_coordinates_and_profiles():
    transit = TransitRouteRequest(**transit_payload())
    street = StreetRouteRequest(
        **transit_payload(profile=StreetRouteProfile.CYCLING)
    )

    assert transit.transit_modes is None
    assert street.profile is StreetRouteProfile.CYCLING


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("origin_lat", -90.1),
        ("destination_lat", 90.1),
        ("origin_lon", -180.1),
        ("destination_lon", 180.1),
    ],
)
def test_routing_schemas_reject_out_of_range_coordinates(field, value):
    with pytest.raises(ValidationError):
        TransitRouteRequest(**transit_payload(**{field: value}))


def test_routing_schemas_reject_identical_points():
    with pytest.raises(ValidationError, match="must be different"):
        StreetRouteRequest(
            origin_lat=55.75,
            origin_lon=37.61,
            destination_lat=55.75,
            destination_lon=37.61,
        )


def test_transit_time_must_be_timezone_aware():
    with pytest.raises(ValidationError, match="timezone"):
        TransitRouteRequest(
            **transit_payload(time=datetime(2026, 7, 12, 18, 40))
        )

    request = TransitRouteRequest(
        **transit_payload(
            time=datetime(2026, 7, 12, 15, 40, tzinfo=timezone.utc)
        )
    )
    assert request.time is not None
    assert request.time.utcoffset() is not None


def test_arrive_by_requires_time():
    with pytest.raises(ValidationError, match="time is required"):
        TransitRouteRequest(**transit_payload(arrive_by=True))


def test_transit_modes_must_not_be_empty_or_mix_transit():
    with pytest.raises(ValidationError, match="must not be empty"):
        TransitRouteRequest(**transit_payload(transit_modes=[]))

    with pytest.raises(ValidationError, match="cannot be combined"):
        TransitRouteRequest(
            **transit_payload(
                transit_modes=[TransitMode.TRANSIT, TransitMode.BUS]
            )
        )


def test_duplicate_transit_modes_are_removed_in_order():
    request = TransitRouteRequest(
        **transit_payload(
            transit_modes=[TransitMode.BUS, TransitMode.SUBWAY, TransitMode.BUS]
        )
    )
    assert request.transit_modes == [TransitMode.BUS, TransitMode.SUBWAY]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_transfers", 11),
        ("max_travel_time_minutes", 0),
        ("min_transfer_time_minutes", 121),
        ("num_itineraries", 6),
        ("search_window_seconds", 7201),
    ],
)
def test_transit_numeric_limits(field, value):
    with pytest.raises(ValidationError):
        TransitRouteRequest(**transit_payload(**{field: value}))


def test_street_profile_rejects_provider_specific_name():
    with pytest.raises(ValidationError):
        StreetRouteRequest(**transit_payload(profile="foot-walking"))

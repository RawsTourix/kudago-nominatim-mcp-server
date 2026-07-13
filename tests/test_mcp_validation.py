from datetime import date, datetime

import pytest
from pydantic import ValidationError

from app.mcp.mappers.time_window import to_utc_window
from app.mcp.reference_data import (
    EventCategory,
    KudaGoLocationSlug,
    PlaceCategory,
)
from app.mcp.schemas.common import Coordinates
from app.mcp.schemas.discovery import (
    FindEventsInput,
    FindPlacesInput,
    ResolveLocationInput,
)
from app.mcp.schemas.routing import (
    PlanPublicTransportInput,
    PlanStreetRouteInput,
    PublicTransportMode,
)


def test_location_source_combinations_are_validated():
    with pytest.raises(ValidationError, match="exactly one"):
        FindEventsInput(date=date(2026, 7, 13))
    with pytest.raises(ValidationError, match="exactly one"):
        FindEventsInput(
            place="Москва",
            location_slug="msk",
            date=date(2026, 7, 13),
        )
    with pytest.raises(ValidationError, match="radius_km is required"):
        FindEventsInput(
            coordinates=Coordinates(latitude=55.75, longitude=37.61),
            date=date(2026, 7, 13),
        )
    with pytest.raises(ValidationError, match="requires coordinates"):
        FindPlacesInput(place="Москва", radius_km=5)


@pytest.mark.parametrize(
    "arguments",
    [
        {"place": "Москва"},
        {"location_slug": KudaGoLocationSlug.MSK},
        {
            "coordinates": Coordinates(latitude=55.75, longitude=37.61),
            "radius_km": 5,
        },
    ],
)
def test_each_supported_location_source_is_valid(arguments):
    assert FindPlacesInput(**arguments)


def test_resolve_location_is_international_without_a_country_filter():
    request = ResolveLocationInput(place="Berlin")
    assert request.country_codes is None


def test_category_enums_do_not_accept_the_other_domain():
    event_value = next(iter(EventCategory)).value
    place_value = next(iter(PlaceCategory)).value
    with pytest.raises(ValidationError):
        FindEventsInput(
            place="Москва",
            date=date(2026, 7, 13),
            categories=[place_value],
        )
    with pytest.raises(ValidationError):
        FindPlacesInput(place="Москва", categories=[event_value])
    with pytest.raises(ValidationError):
        FindPlacesInput(place="Москва", categories=["museum"])


def test_calendar_window_validation_and_utc_boundaries():
    with pytest.raises(ValidationError, match="provided together"):
        FindEventsInput(
            place="Москва",
            date_from=date(2026, 7, 13),
        )
    with pytest.raises(ValidationError, match="31 days"):
        FindEventsInput(
            place="Москва",
            date_from=date(2026, 7, 1),
            date_to=date(2026, 8, 1),
        )
    request = FindEventsInput(
        place="Москва",
        date=date(2026, 7, 13),
        timezone="Europe/Moscow",
    )
    assert to_utc_window(
        single_date=request.date,
        date_from=request.date_from,
        date_to=request.date_to,
        timezone_name=request.timezone,
    ) == (1783890000, 1783976399)

    fixed_offset = FindEventsInput(
        place="Москва",
        date=date(2026, 7, 13),
        timezone="+03:00",
    )
    assert to_utc_window(
        single_date=fixed_offset.date,
        date_from=fixed_offset.date_from,
        date_to=fixed_offset.date_to,
        timezone_name=fixed_offset.timezone,
    ) == (1783890000, 1783976399)

    with pytest.raises(ValidationError, match="IANA timezone"):
        FindEventsInput(
            place="Москва",
            date=date(2026, 7, 13),
            timezone="Mars/Olympus_Mons",
        )
    with pytest.raises(ValidationError, match="cannot be combined"):
        FindEventsInput(
            place="Москва",
            date=date(2026, 7, 13),
            date_from=date(2026, 7, 13),
            date_to=date(2026, 7, 14),
        )


def test_routing_rejects_naive_time_and_conflicting_time_semantics():
    origin = Coordinates(latitude=55.75, longitude=37.61)
    destination = Coordinates(latitude=55.76, longitude=37.62)
    with pytest.raises(ValidationError, match="timezone"):
        PlanPublicTransportInput(
            origin=origin,
            destination=destination,
            departure_time=datetime(2026, 7, 13, 12, 0),
        )
    with pytest.raises(ValidationError, match="cannot be provided together"):
        PlanPublicTransportInput(
            origin=origin,
            destination=destination,
            departure_time="2026-07-13T12:00:00+03:00",
            arrival_time="2026-07-13T13:00:00+03:00",
        )

    with pytest.raises(ValidationError, match="must be different"):
        PlanStreetRouteInput(origin=origin, destination=origin)


def test_routing_modes_are_a_deduplicated_agent_enum():
    request = PlanPublicTransportInput(
        origin=Coordinates(latitude=55.75, longitude=37.61),
        destination=Coordinates(latitude=55.76, longitude=37.62),
        modes=[PublicTransportMode.SUBWAY, PublicTransportMode.SUBWAY],
    )
    assert request.modes == [PublicTransportMode.SUBWAY]
    with pytest.raises(ValidationError):
        PlanPublicTransportInput(
            origin=Coordinates(latitude=55.75, longitude=37.61),
            destination=Coordinates(latitude=55.76, longitude=37.62),
            modes=["TRANSIT"],
        )

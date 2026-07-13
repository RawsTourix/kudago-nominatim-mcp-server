from __future__ import annotations

from datetime import datetime, timezone

from app.mcp.schemas.routing import PublicTransportMode, StreetTravelMode
from app.schemas.routing import StreetRouteProfile, TransitMode


PUBLIC_TRANSPORT_MODE_MAP = {
    PublicTransportMode.TRAM: TransitMode.TRAM,
    PublicTransportMode.SUBWAY: TransitMode.SUBWAY,
    PublicTransportMode.FERRY: TransitMode.FERRY,
    PublicTransportMode.BUS: TransitMode.BUS,
    PublicTransportMode.COACH: TransitMode.COACH,
    PublicTransportMode.RAIL: TransitMode.RAIL,
    PublicTransportMode.HIGH_SPEED_RAIL: TransitMode.HIGHSPEED_RAIL,
    PublicTransportMode.LONG_DISTANCE_RAIL: TransitMode.LONG_DISTANCE,
    PublicTransportMode.NIGHT_RAIL: TransitMode.NIGHT_RAIL,
    PublicTransportMode.REGIONAL_RAIL: TransitMode.REGIONAL_RAIL,
    PublicTransportMode.SUBURBAN_RAIL: TransitMode.SUBURBAN,
    PublicTransportMode.FUNICULAR: TransitMode.FUNICULAR,
    PublicTransportMode.AERIAL_LIFT: TransitMode.AERIAL_LIFT,
}
STREET_MODE_MAP = {
    StreetTravelMode.WALKING: StreetRouteProfile.WALKING,
    StreetTravelMode.CYCLING: StreetRouteProfile.CYCLING,
    StreetTravelMode.DRIVING: StreetRouteProfile.DRIVING,
}


def transit_time(
    departure_time: datetime | None,
    arrival_time: datetime | None,
) -> tuple[datetime, bool]:
    if arrival_time is not None:
        return arrival_time, True
    return departure_time or datetime.now(timezone.utc), False


def transit_modes(
    modes: list[PublicTransportMode] | None,
) -> list[TransitMode] | None:
    if modes is None:
        return None
    return [PUBLIC_TRANSPORT_MODE_MAP[mode] for mode in modes]


__all__ = [
    "PUBLIC_TRANSPORT_MODE_MAP",
    "STREET_MODE_MAP",
    "transit_modes",
    "transit_time",
]

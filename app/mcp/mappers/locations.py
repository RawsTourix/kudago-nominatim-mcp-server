from __future__ import annotations

from enum import StrEnum
from typing import Any

from app.mcp.schemas.common import Coordinates


def location_payload(
    *,
    place: str | None,
    location_slug: StrEnum | None,
    coordinates: Coordinates | None,
    radius_km: float | None,
) -> dict[str, Any]:
    return {
        "location": location_slug.value if location_slug is not None else None,
        "place_query": place,
        "lat": coordinates.latitude if coordinates is not None else None,
        "lon": coordinates.longitude if coordinates is not None else None,
        "radius": (
            int(round(radius_km * 1000)) if radius_km is not None else None
        ),
    }


def city_payload(
    *,
    city: str | None,
    location_slug: StrEnum | None,
) -> dict[str, str | None]:
    return {
        "location": location_slug.value if location_slug is not None else None,
        "place_query": city,
    }


__all__ = ["city_payload", "location_payload"]

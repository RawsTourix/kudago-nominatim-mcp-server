from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Literal
from weakref import WeakKeyDictionary

from kudago_mcp_client import KudaGoHttpClient
from kudago_mcp_client import locations as kudago_locations
from nominatim_geo_client import NominatimHttpClient, search

from kudago_nominatim_utils import first_list_items, normalize_text

GeoKind = Literal["none", "kudago_location", "coordinates"]
GeoStatus = Literal[
    "ok",
    "ambiguous_place",
    "place_not_found",
    "invalid_coordinates",
    "unsupported",
    "geocoding_error",
]

_locations_cache: WeakKeyDictionary[KudaGoHttpClient, dict[str, tuple[float, list[dict[str, Any]]]]] = WeakKeyDictionary()
_locations_locks: WeakKeyDictionary[KudaGoHttpClient, asyncio.Lock] = WeakKeyDictionary()


@dataclass(slots=True)
class ResolvedGeo:
    status: GeoStatus
    kind: GeoKind = "none"
    location: str | None = None
    lat: float | None = None
    lon: float | None = None
    radius: int | None = None
    message: str | None = None
    candidates: list[dict[str, Any]] | None = None
    matched_location: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "kind": self.kind,
            "location": self.location,
            "lat": self.lat,
            "lon": self.lon,
            "radius": self.radius,
            "message": self.message,
            "candidates": self.candidates or [],
            "matched_location": self.matched_location,
        }


def _candidate_lat_lon(candidate: dict[str, Any]) -> tuple[float | None, float | None]:
    try:
        return float(candidate.get("lat")), float(candidate.get("lon"))
    except (TypeError, ValueError):
        return None, None


def _candidate_radius(candidate: dict[str, Any], default_radius: int) -> int:
    bbox = candidate.get("boundingbox")
    if isinstance(bbox, list) and len(bbox) == 4:
        try:
            south, north, west, east = [float(item) for item in bbox]
            lat_span_m = abs(north - south) * 111_000
            lon_span_m = abs(east - west) * 111_000
            radius = int(max(lat_span_m, lon_span_m, 2_000) / 2)
            return max(5_000, min(radius, 100_000))
        except (TypeError, ValueError):
            pass
    return default_radius


async def _get_kudago_locations(
    client: KudaGoHttpClient,
    *,
    lang: str,
    cache_ttl: float,
) -> list[dict[str, Any]]:
    now = time.monotonic()
    cached = _locations_cache.get(client, {}).get(lang)
    if cached is not None and now - cached[0] < cache_ttl:
        return cached[1]

    lock = _locations_locks.setdefault(client, asyncio.Lock())
    async with lock:
        now = time.monotonic()
        cached = _locations_cache.get(client, {}).get(lang)
        if cached is not None and now - cached[0] < cache_ttl:
            return cached[1]

        data = await kudago_locations(client, lang=lang, fields=["slug", "name", "timezone", "coords"])
        locations = [item for item in first_list_items(data, limit=10_000) if isinstance(item, dict)]
        if cache_ttl > 0:
            _locations_cache.setdefault(client, {})[lang] = (now, locations)
        return locations


async def find_kudago_location(
    client: KudaGoHttpClient,
    query: str,
    *,
    lang: str = "ru",
    cache_ttl: float = 900.0,
) -> dict[str, Any] | None:
    """Find an exact KudaGo location by slug or localized name."""
    needle = normalize_text(query)
    if not needle:
        return None
    for item in await _get_kudago_locations(client, lang=lang, cache_ttl=max(0.0, cache_ttl)):
        slug = str(item.get("slug") or "")
        name = str(item.get("name") or "")
        if normalize_text(slug) == needle or normalize_text(name) == needle:
            return item
    return None


async def resolve_geo_for_kudago(
    *,
    kudago_client: KudaGoHttpClient,
    nominatim_client: NominatimHttpClient,
    location: str | None = None,
    place_query: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    radius: int | None = None,
    allow_coordinates: bool = True,
    lang: str = "ru",
    countrycodes: str | list[str] | None = "ru",
    default_radius: int = 50_000,
    geocode_limit: int = 5,
    email: str | None = None,
    locations_cache_ttl: float = 900.0,
) -> ResolvedGeo:
    """Resolve tool-level geo arguments into KudaGo location or coordinates."""
    if location:
        return ResolvedGeo(status="ok", kind="kudago_location", location=location.strip())

    has_lat_lon = lat is not None or lon is not None
    if has_lat_lon:
        if lat is None or lon is None or radius is None:
            return ResolvedGeo(status="invalid_coordinates", message="lat, lon and radius must be provided together. If you pass place_query, radius may be used without lat/lon.")
        if not allow_coordinates:
            return ResolvedGeo(status="unsupported", message="This endpoint does not support coordinates; use a KudaGo location slug.")
        return ResolvedGeo(status="ok", kind="coordinates", lat=lat, lon=lon, radius=radius)

    if radius is not None and not place_query:
        return ResolvedGeo(status="invalid_coordinates", message="radius without lat/lon requires place_query, or pass lat, lon and radius together.")

    if not place_query:
        return ResolvedGeo(status="ok", kind="none")

    matched = await find_kudago_location(kudago_client, place_query, lang=lang, cache_ttl=locations_cache_ttl)
    if matched is not None:
        return ResolvedGeo(status="ok", kind="kudago_location", location=str(matched.get("slug")), matched_location=matched)

    if not allow_coordinates:
        return ResolvedGeo(status="unsupported", message="KudaGo location was not found and this endpoint does not support coordinates.")

    try:
        candidates_raw = await search(
            nominatim_client,
            q=place_query,
            countrycodes=countrycodes,
            limit=geocode_limit,
            accept_language=lang,
            addressdetails=True,
            namedetails=True,
            email=email,
        )
    except Exception as exc:
        return ResolvedGeo(status="geocoding_error", message=f"Nominatim geocoding failed: {exc}")

    candidates = candidates_raw if isinstance(candidates_raw, list) else []
    candidates = [item for item in candidates if isinstance(item, dict)]
    if not candidates:
        return ResolvedGeo(status="place_not_found", message="No KudaGo location or Nominatim candidate was found for place_query.")
    if len(candidates) > 1:
        return ResolvedGeo(status="ambiguous_place", message="Several Nominatim candidates were found. Pick one and call the tool again with explicit lat, lon and radius.", candidates=candidates)

    selected = candidates[0]
    selected_lat, selected_lon = _candidate_lat_lon(selected)
    if selected_lat is None or selected_lon is None:
        return ResolvedGeo(status="place_not_found", message="Nominatim candidate has no usable lat/lon.", candidates=candidates)
    return ResolvedGeo(status="ok", kind="coordinates", lat=selected_lat, lon=selected_lon, radius=radius or _candidate_radius(selected, default_radius), candidates=candidates)

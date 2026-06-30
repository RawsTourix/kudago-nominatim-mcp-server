from __future__ import annotations

import httpx
import pytest

from kudago_mcp_client import KudaGoHttpClient
from kudago_nominatim_geo import resolve_geo_for_kudago
from nominatim_geo_client import NominatimHttpClient


@pytest.mark.asyncio
async def test_place_query_with_radius_uses_nominatim_not_invalid_coordinates() -> None:
    seen_nominatim: dict[str, str] = {}

    def kudago_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    def nominatim_handler(request: httpx.Request) -> httpx.Response:
        seen_nominatim.update(dict(request.url.params))
        return httpx.Response(200, json=[{"place_id": 1, "display_name": "Нахабино", "lat": "55.8422", "lon": "37.1778", "boundingbox": ["55.80", "55.88", "37.12", "37.24"]}])

    async with KudaGoHttpClient(transport=httpx.MockTransport(kudago_handler)) as kudago_client:
        async with NominatimHttpClient(transport=httpx.MockTransport(nominatim_handler), min_interval_seconds=0, user_agent="test-suite/0.1") as nominatim_client:
            geo = await resolve_geo_for_kudago(kudago_client=kudago_client, nominatim_client=nominatim_client, place_query="Нахабино", radius=15000, countrycodes="ru")

    assert geo.status == "ok"
    assert geo.kind == "coordinates"
    assert geo.lat == pytest.approx(55.8422)
    assert geo.lon == pytest.approx(37.1778)
    assert geo.radius == 15000
    assert seen_nominatim["q"] == "Нахабино"
    assert seen_nominatim["featureType"] == "settlement"


@pytest.mark.asyncio
async def test_nominatim_api_error_becomes_controlled_geo_error() -> None:
    def kudago_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    def nominatim_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "Access denied"})

    async with KudaGoHttpClient(transport=httpx.MockTransport(kudago_handler)) as kudago_client:
        async with NominatimHttpClient(transport=httpx.MockTransport(nominatim_handler), min_interval_seconds=0, user_agent="test-suite/0.1") as nominatim_client:
            geo = await resolve_geo_for_kudago(kudago_client=kudago_client, nominatim_client=nominatim_client, place_query="Нахабино", radius=15000, countrycodes="ru")

    assert geo.status == "geocoding_error"
    assert "Nominatim geocoding failed" in (geo.message or "")

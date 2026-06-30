from __future__ import annotations

import httpx
import pytest

from nominatim_geo_client import NominatimHttpClient, search, search_settlement, search_structured
from nominatim_geo_client.http_client import NominatimAPIError, NominatimParameterError, bool_int, comma_join


def test_comma_join_and_bool_int() -> None:
    assert comma_join(["ru", "de"]) == "ru,de"
    assert comma_join("ru,de") == "ru,de"
    assert comma_join([]) is None
    assert bool_int(True) == 1
    assert bool_int(False) == 0
    with pytest.raises(NominatimParameterError):
        bool_int(2)


@pytest.mark.asyncio
async def test_search_builds_free_form_query() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, json=[{"lat": "55.75", "lon": "37.61"}])

    async with NominatimHttpClient(transport=httpx.MockTransport(handler), min_interval_seconds=0, user_agent="test-suite/0.1") as client:
        data = await search(client, q="Москва", countrycodes=["ru"], layer=["address"], featureType="city", addressdetails=True, limit=5)

    assert isinstance(data, list)
    assert seen["q"] == "Москва"
    assert seen["format"] == "jsonv2"
    assert seen["countrycodes"] == "ru"
    assert seen["layer"] == "address"
    assert seen["featureType"] == "city"
    assert seen["addressdetails"] == "1"
    assert seen["limit"] == "5"


@pytest.mark.asyncio
async def test_search_structured_has_no_q_param() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, json=[])

    async with NominatimHttpClient(transport=httpx.MockTransport(handler), min_interval_seconds=0, user_agent="test-suite/0.1") as client:
        await search_structured(client, city="Berlin", country="Germany", limit=3)

    assert "q" not in seen
    assert seen["city"] == "Berlin"
    assert seen["country"] == "Germany"
    assert seen["limit"] == "3"


@pytest.mark.asyncio
async def test_search_settlement_sets_feature_type() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, json=[])

    async with NominatimHttpClient(transport=httpx.MockTransport(handler), min_interval_seconds=0, user_agent="test-suite/0.1") as client:
        await search_settlement(client, q="Казань", countrycodes=["ru"], email="test@example.com")

    assert seen["q"] == "Казань"
    assert seen["featureType"] == "settlement"
    assert seen["accept-language"] == "ru"
    assert seen["addressdetails"] == "1"
    assert seen["email"] == "test@example.com"


@pytest.mark.asyncio
async def test_client_raises_api_error() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(429, json={"error": "Too many requests"}))
    async with NominatimHttpClient(transport=transport, min_interval_seconds=0, user_agent="test-suite/0.1") as client:
        with pytest.raises(NominatimAPIError) as exc_info:
            await client.get("search", {"q": "test"})
    assert exc_info.value.status_code == 429
    assert "Too many requests" in str(exc_info.value)

from __future__ import annotations

import httpx
import pytest

from kudago_mcp_client import KudaGoHttpClient, event, events, movie_showings_for_movie, search


@pytest.mark.asyncio
async def test_events_endpoint_builds_expected_query() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"count": 0, "results": []})

    transport = httpx.MockTransport(handler)
    async with KudaGoHttpClient(transport=transport) as client:
        await events(client, location="msk", fields=["id", "title"], categories=["concert", "-kids"], is_free=True, page_size=5)

    assert "https://kudago.com/public-api/v1.4/events/" in seen["url"]
    assert "location=msk" in seen["url"]
    assert "fields=id%2Ctitle" in seen["url"]
    assert "categories=concert%2C-kids" in seen["url"]
    assert "is_free=true" in seen["url"]
    assert "page_size=5" in seen["url"]


@pytest.mark.asyncio
async def test_path_segments_are_escaped() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"id": 1})

    transport = httpx.MockTransport(handler)
    async with KudaGoHttpClient(transport=transport) as client:
        await event(client, 123, fields="id,title")

    assert seen["url"].startswith("https://kudago.com/public-api/v1.4/events/123/")
    assert "fields=id%2Ctitle" in seen["url"]


@pytest.mark.asyncio
async def test_search_and_movie_showings_for_movie() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path + ("?" + request.url.query.decode() if request.url.query else ""))
        return httpx.Response(200, json={"count": 0, "results": []})

    transport = httpx.MockTransport(handler)
    async with KudaGoHttpClient(transport=transport) as client:
        await search(client, "джаз", ctype="event", location="msk")
        await movie_showings_for_movie(client, 1705, location="spb", place=14918)

    assert paths[0].startswith("/public-api/v1.4/search/?")
    assert "q=" in paths[0]
    assert "ctype=event" in paths[0]
    assert paths[1].startswith("/public-api/v1.4/movies/1705/showings/?")
    assert "place=14918" in paths[1]

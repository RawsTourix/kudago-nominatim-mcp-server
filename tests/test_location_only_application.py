from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.contracts import ExecutionContext
from app.application.handlers.lists import ListsSearchHandler
from app.application.handlers.news import NewsSearchHandler


def resolver(result):
    return SimpleNamespace(
        resolve_for_kudago_location_or_coordinates=AsyncMock(return_value=result)
    )


@pytest.mark.asyncio
async def test_news_handler_returns_search_result_and_filters():
    job_id = uuid4()
    handler = NewsSearchHandler.__new__(NewsSearchHandler)
    handler.location_resolver = resolver(
        {
            "status": "ok",
            "location": "msk",
            "geo": {"status": "ok", "kind": "kudago_location"},
        }
    )
    handler.news_service = SimpleNamespace(
        search_news=AsyncMock(
            return_value={
                "count": 1,
                "returned": 1,
                "items": [{"id": 1, "title": "News"}],
            }
        )
    )

    output = await handler.run(
        ExecutionContext(job_id, "news.search", "test"),
        {
            "location": "msk",
            "tags": "music",
            "actual_only": True,
            "page_size": 3,
            "lang": "ru",
        },
    )

    assert output.status == "ok"
    assert output.items == [{"id": 1, "title": "News"}]
    assert output.result_payload["filters"] == {
        "location": "msk",
        "place_query": None,
        "tags": "music",
        "actual_only": True,
    }
    handler.news_service.search_news.assert_awaited_once_with(
        job_id=job_id,
        location="msk",
        tags="music",
        actual_only=True,
        page=1,
        page_size=3,
        lang="ru",
    )


@pytest.mark.asyncio
async def test_lists_handler_returns_search_result_and_filters():
    job_id = uuid4()
    handler = ListsSearchHandler.__new__(ListsSearchHandler)
    handler.location_resolver = resolver(
        {
            "status": "ok",
            "location": "msk",
            "geo": {"status": "ok", "kind": "kudago_location"},
        }
    )
    handler.lists_service = SimpleNamespace(
        search_lists=AsyncMock(
            return_value={
                "count": 1,
                "returned": 1,
                "items": [{"id": 2, "title": "List"}],
            }
        )
    )

    output = await handler.run(
        ExecutionContext(job_id, "lists.search", "test"),
        {"location": "msk", "tags": "weekend", "page_size": 3, "lang": "ru"},
    )

    assert output.status == "ok"
    assert output.items == [{"id": 2, "title": "List"}]
    assert output.result_payload["filters"] == {
        "location": "msk",
        "place_query": None,
        "tags": "weekend",
    }
    handler.lists_service.search_lists.assert_awaited_once_with(
        job_id=job_id,
        location="msk",
        tags="weekend",
        page=1,
        page_size=3,
        lang="ru",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler_class", "service_attribute", "method_name", "command"),
    [
        (NewsSearchHandler, "news_service", "search_news", "news.search"),
        (ListsSearchHandler, "lists_service", "search_lists", "lists.search"),
    ],
)
async def test_location_only_handlers_return_geo_ambiguity_without_kudago_call(
    handler_class,
    service_attribute,
    method_name,
    command,
):
    handler = handler_class.__new__(handler_class)
    handler.location_resolver = resolver(
        {
            "status": "geo_ambiguous",
            "location": None,
            "geo": {
                "status": "ambiguous",
                "kind": "none",
                "candidates": [{"display_name": "First"}],
            },
        }
    )
    search_method = AsyncMock()
    setattr(handler, service_attribute, SimpleNamespace(**{method_name: search_method}))

    output = await handler.run(
        ExecutionContext(uuid4(), command, "test"),
        {"place_query": "Springfield", "lang": "ru"},
    )

    assert output.status == "geo_ambiguous"
    assert output.items == []
    assert output.result_payload["message"] == (
        "Geo resolution is ambiguous; specify a KudaGo location slug."
    )
    search_method.assert_not_awaited()

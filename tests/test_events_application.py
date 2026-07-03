from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.contracts import ExecutionContext
from app.application.handlers.events import EventsSearchHandler


def make_handler(*, resolved, search_result=None) -> EventsSearchHandler:
    handler = EventsSearchHandler.__new__(EventsSearchHandler)
    handler.location_resolver = SimpleNamespace(
        resolve_for_kudago_location_or_coordinates=AsyncMock(
            return_value=resolved
        )
    )
    handler.events_service = SimpleNamespace(
        search_events=AsyncMock(return_value=search_result)
    )
    return handler


@pytest.mark.asyncio
async def test_events_handler_returns_search_result_and_filters():
    job_id = uuid4()
    geo = {
        "status": "ok",
        "kind": "kudago_location",
        "location": "msk",
    }
    handler = make_handler(
        resolved={
            "status": "ok",
            "location": "msk",
            "lat": None,
            "lon": None,
            "radius": None,
            "geo": geo,
        },
        search_result={
            "status": "ok",
            "count": 20,
            "returned": 1,
            "items": [{"id": 42, "title": "Concert"}],
        },
    )
    payload = {
        "location": "msk",
        "actual_since": 1_700_000_000,
        "categories": "concert",
        "page_size": 3,
        "lang": "ru",
    }

    output = await handler.run(
        ExecutionContext(job_id, "events.search", "test"),
        payload,
    )

    assert output.status == "ok"
    assert output.result_type == "events.search"
    assert output.items == [{"id": 42, "title": "Concert"}]
    assert output.result_payload["geo"] == geo
    assert output.result_payload["filters"]["actual_since"] == 1_700_000_000
    handler.events_service.search_events.assert_awaited_once_with(
        job_id=job_id,
        location="msk",
        lat=None,
        lon=None,
        radius=None,
        actual_since=1_700_000_000,
        actual_until=None,
        categories="concert",
        tags=None,
        is_free=None,
        page=1,
        page_size=3,
        lang="ru",
    )


@pytest.mark.asyncio
async def test_events_handler_returns_geo_ambiguity_without_kudago_call():
    geo = {
        "status": "ambiguous",
        "kind": "none",
        "candidates": [{"display_name": "First"}, {"display_name": "Second"}],
    }
    handler = make_handler(
        resolved={
            "status": "geo_ambiguous",
            "location": None,
            "lat": None,
            "lon": None,
            "radius": None,
            "geo": geo,
        }
    )

    output = await handler.run(
        ExecutionContext(uuid4(), "events.search", "test"),
        {"place_query": "Springfield", "lang": "ru"},
    )

    assert output.status == "geo_ambiguous"
    assert output.items == []
    assert output.result_payload == {
        "status": "geo_ambiguous",
        "message": (
            "Geo resolution is ambiguous; choose one candidate or pass "
            "coordinates."
        ),
        "geo": geo,
        "items": [],
        "count": 0,
        "returned": 0,
    }
    handler.events_service.search_events.assert_not_awaited()


@pytest.mark.asyncio
async def test_events_handler_emits_actual_since_defaulted_event():
    handler = make_handler(
        resolved={
            "status": "ok",
            "location": "msk",
            "lat": None,
            "lon": None,
            "radius": None,
            "geo": {"status": "ok", "kind": "kudago_location"},
        },
        search_result={"count": 0, "returned": 0, "items": []},
    )

    output = await handler.run(
        ExecutionContext(uuid4(), "events.search", "test"),
        {"location": "msk", "lang": "ru"},
    )

    assert len(output.events) == 1
    event = output.events[0]
    assert event.event_type == "actual_since_defaulted"
    assert event.data["actual_since"] == output.result_payload["filters"][
        "actual_since"
    ]

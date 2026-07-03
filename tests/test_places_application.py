from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.contracts import ExecutionContext
from app.application.handlers.places import PlacesSearchHandler


def make_handler(*, resolved, search_result=None) -> PlacesSearchHandler:
    handler = PlacesSearchHandler.__new__(PlacesSearchHandler)
    handler.location_resolver = SimpleNamespace(
        resolve_for_kudago_location_or_coordinates=AsyncMock(
            return_value=resolved
        )
    )
    handler.places_service = SimpleNamespace(
        search_places=AsyncMock(return_value=search_result)
    )
    return handler


@pytest.mark.asyncio
async def test_places_handler_defaults_showing_window_and_emits_event():
    job_id = uuid4()
    handler = make_handler(
        resolved={
            "status": "ok",
            "location": "msk",
            "lat": None,
            "lon": None,
            "radius": None,
            "geo": {
                "status": "ok",
                "kind": "kudago_location",
                "location": "msk",
            },
        },
        search_result={
            "count": 1,
            "returned": 1,
            "items": [{"id": 7, "title": "Cinema"}],
        },
    )

    output = await handler.run(
        ExecutionContext(job_id, "places.search", "test"),
        {"location": "msk", "has_showings": True, "page_size": 3, "lang": "ru"},
    )

    filters = output.result_payload["filters"]
    assert output.status == "ok"
    assert output.items == [{"id": 7, "title": "Cinema"}]
    assert filters["showing_until"] - filters["showing_since"] == 7 * 24 * 60 * 60
    assert len(output.events) == 1
    assert output.events[0].event_type == "showing_window_defaulted"
    assert output.events[0].data == {
        "showing_since": filters["showing_since"],
        "showing_until": filters["showing_until"],
    }
    call = handler.places_service.search_places.await_args.kwargs
    assert call["job_id"] == job_id
    assert call["showing_since"] == filters["showing_since"]
    assert call["showing_until"] == filters["showing_until"]


@pytest.mark.asyncio
async def test_places_handler_returns_geo_ambiguity_without_kudago_call():
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
        ExecutionContext(uuid4(), "places.search", "test"),
        {"place_query": "Springfield", "lang": "ru"},
    )

    assert output.status == "geo_ambiguous"
    assert output.items == []
    assert output.result_payload["geo"] == geo
    handler.places_service.search_places.assert_not_awaited()

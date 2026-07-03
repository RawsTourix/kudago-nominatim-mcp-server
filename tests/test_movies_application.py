from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.contracts import ExecutionContext
from app.application.handlers.movie_showings import MovieShowingsSearchHandler
from app.application.handlers.movies import MoviesSearchHandler


def resolver(result):
    return SimpleNamespace(
        resolve_for_kudago_location_or_coordinates=AsyncMock(return_value=result)
    )


def resolved_moscow():
    return {
        "status": "ok",
        "location": "msk",
        "geo": {"status": "ok", "kind": "kudago_location", "location": "msk"},
    }


@pytest.mark.asyncio
async def test_movies_handler_defaults_actual_since_and_emits_event():
    job_id = uuid4()
    handler = MoviesSearchHandler.__new__(MoviesSearchHandler)
    handler.location_resolver = resolver(resolved_moscow())
    handler.movies_service = SimpleNamespace(
        search_movies=AsyncMock(
            return_value={"count": 1, "returned": 1, "items": [{"id": 10}]}
        )
    )

    output = await handler.run(
        ExecutionContext(job_id, "movies.search", "test"),
        {"location": "msk", "page_size": 3, "lang": "ru"},
    )

    actual_since = output.result_payload["filters"]["actual_since"]
    assert output.status == "ok"
    assert output.items == [{"id": 10}]
    assert len(output.events) == 1
    assert output.events[0].event_type == "actual_since_defaulted"
    assert output.events[0].data == {"actual_since": actual_since}
    assert handler.movies_service.search_movies.await_args.kwargs[
        "actual_since"
    ] == actual_since


@pytest.mark.asyncio
async def test_movie_showings_handler_defaults_window_and_passes_movie_id():
    job_id = uuid4()
    handler = MovieShowingsSearchHandler.__new__(MovieShowingsSearchHandler)
    handler.location_resolver = resolver(resolved_moscow())
    handler.movie_showings_service = SimpleNamespace(
        search_movie_showings=AsyncMock(
            return_value={"count": 1, "returned": 1, "items": [{"id": 11}]}
        )
    )

    output = await handler.run(
        ExecutionContext(job_id, "movie_showings.search", "test"),
        {"location": "msk", "movie_id": 42, "page_size": 3, "lang": "ru"},
    )

    filters = output.result_payload["filters"]
    assert output.status == "ok"
    assert output.items == [{"id": 11}]
    assert filters["actual_until"] - filters["actual_since"] == 7 * 24 * 60 * 60
    assert len(output.events) == 1
    assert output.events[0].event_type == "actual_window_defaulted"
    call = handler.movie_showings_service.search_movie_showings.await_args.kwargs
    assert call["movie_id"] == 42
    assert call["actual_since"] == filters["actual_since"]
    assert call["actual_until"] == filters["actual_until"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler_class", "service_attribute", "method_name", "command", "status"),
    [
        (MoviesSearchHandler, "movies_service", "search_movies", "movies.search", "geo_ambiguous"),
        (MoviesSearchHandler, "movies_service", "search_movies", "movies.search", "geo_unsupported"),
        (
            MovieShowingsSearchHandler,
            "movie_showings_service",
            "search_movie_showings",
            "movie_showings.search",
            "geo_ambiguous",
        ),
        (
            MovieShowingsSearchHandler,
            "movie_showings_service",
            "search_movie_showings",
            "movie_showings.search",
            "geo_unsupported",
        ),
    ],
)
async def test_movie_handlers_return_geo_status_without_kudago_call(
    handler_class,
    service_attribute,
    method_name,
    command,
    status,
):
    handler = handler_class.__new__(handler_class)
    handler.location_resolver = resolver(
        {
            "status": status,
            "location": None,
            "geo": {"status": status.removeprefix("geo_"), "kind": "none"},
        }
    )
    search_method = AsyncMock()
    setattr(handler, service_attribute, SimpleNamespace(**{method_name: search_method}))

    output = await handler.run(
        ExecutionContext(uuid4(), command, "test"),
        {"place_query": "Springfield", "lang": "ru"},
    )

    assert output.status == status
    assert output.items == []
    if status == "geo_unsupported":
        assert "Coordinates are not supported" in output.result_payload["message"]
    search_method.assert_not_awaited()

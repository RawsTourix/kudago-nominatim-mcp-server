from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.contracts import ExecutionContext
from app.application.handlers.objects import ObjectDetailHandler
from app.application.handlers.references import ReferenceHandler
from app.integrations.kudago import KudaGoHttpClient
from app.services.object_service import ObjectService
from app.services.tracked_kudago_client import TrackedKudaGoHttpClient


@pytest.mark.asyncio
async def test_reference_handler_returns_locations_as_items():
    job_id = uuid4()
    handler = ReferenceHandler.__new__(ReferenceHandler)
    handler.reference_service = SimpleNamespace(
        get_locations=AsyncMock(
            return_value={
                "status": "ok",
                "kind": "locations",
                "data": [{"slug": "msk", "name": "Moscow"}],
            }
        )
    )

    output = await handler.run(
        ExecutionContext(job_id, "reference.get", "test"),
        {"kind": "locations", "lang": "ru"},
    )

    assert output.status == "ok"
    assert output.items == [{"slug": "msk", "name": "Moscow"}]
    handler.reference_service.get_locations.assert_awaited_once_with(
        lang="ru",
        job_id=job_id,
    )


@pytest.mark.asyncio
async def test_object_handler_returns_detail_as_item():
    job_id = uuid4()
    handler = ObjectDetailHandler.__new__(ObjectDetailHandler)
    handler.object_service = SimpleNamespace(
        get_object_detail=AsyncMock(
            return_value={
                "status": "ok",
                "object_type": "location",
                "object_id": "msk",
                "data": {"slug": "msk", "name": "Moscow"},
                "comments": None,
                "showings": None,
            }
        )
    )

    output = await handler.run(
        ExecutionContext(job_id, "object.detail", "test"),
        {"object_type": "location", "object_id": "msk", "lang": "ru"},
    )

    assert output.status == "ok"
    assert output.items == [{"slug": "msk", "name": "Moscow"}]
    handler.object_service.get_object_detail.assert_awaited_once_with(
        object_type="location",
        object_id="msk",
        include_comments=False,
        include_showings=False,
        lang="ru",
        job_id=job_id,
    )


@pytest.mark.asyncio
async def test_tracked_kudago_client_records_real_get(monkeypatch):
    data = {"slug": "msk"}
    parent_get = AsyncMock(return_value=data)
    monkeypatch.setattr(KudaGoHttpClient, "get", parent_get)
    upstream_repo = SimpleNamespace(create=AsyncMock())
    job_id = uuid4()
    client = TrackedKudaGoHttpClient(
        job_id=job_id,
        upstream_call_repo=upstream_repo,
        operation_prefix="reference",
    )

    try:
        result = await client.get("locations/msk/", {"lang": "ru"})
    finally:
        await client.aclose()

    assert result == data
    parent_get.assert_awaited_once_with("locations/msk/", {"lang": "ru"})
    upstream_repo.create.assert_awaited_once()
    call = upstream_repo.create.await_args.kwargs
    assert call["job_id"] == job_id
    assert call["operation"] == "reference.locations.msk"
    assert call["url_path"] == "/locations/msk/"
    assert call["request_payload"] == {"lang": "ru"}
    assert call["response_payload"] == data
    assert call["success"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("object_type", "include_comments", "include_showings", "operations"),
    [
        (
            "event",
            True,
            False,
            ["object.events.123", "object.events.123.comments"],
        ),
        (
            "movie",
            False,
            True,
            ["object.movies.123", "object.movies.123.showings"],
        ),
    ],
)
async def test_object_service_tracks_each_upstream_detail_call(
    monkeypatch,
    object_type,
    include_comments,
    include_showings,
    operations,
):
    monkeypatch.setattr(KudaGoHttpClient, "get", AsyncMock(return_value={}))
    upstream_repo = SimpleNamespace(create=AsyncMock())
    service = ObjectService(SimpleNamespace())
    service.upstream_call_repo = upstream_repo

    await service.get_object_detail(
        object_type=object_type,
        object_id="123",
        include_comments=include_comments,
        include_showings=include_showings,
        job_id=uuid4(),
    )

    assert [
        call.kwargs["operation"] for call in upstream_repo.create.await_args_list
    ] == operations

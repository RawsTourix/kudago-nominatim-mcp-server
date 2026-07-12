from datetime import datetime, timezone

import httpx
import pytest

from app.integrations.transitous import (
    TransitousConfigurationError,
    TransitousHttpClient,
    TransitousInvalidResponseError,
    TransitousResponseError,
    TransitousTransportError,
    plan_journey,
)


def test_transitous_client_requires_user_agent_only_when_constructed():
    with pytest.raises(TransitousConfigurationError, match="USER_AGENT"):
        TransitousHttpClient(user_agent=None, trust_env=False)


@pytest.mark.asyncio
async def test_transitous_plan_serializes_required_parameters():
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        return httpx.Response(200, json={"itineraries": []})

    client = TransitousHttpClient(
        user_agent="routing-tests/0.1 tests@example.com",
        transport=httpx.MockTransport(handler),
        trust_env=False,
    )
    result = await plan_journey(
        client,
        from_place="55.842,37.18",
        to_place="55.751,37.617",
        time=datetime(2026, 7, 12, 18, 40, tzinfo=timezone.utc),
        arrive_by=True,
        transit_modes=["SUBURBAN", "SUBWAY", "BUS"],
        max_transfers=2,
        max_travel_time=120,
        min_transfer_time=5,
        num_itineraries=3,
        search_window=900,
        language="ru",
    )
    await client.aclose()

    request = seen["request"]
    params = request.url.params
    assert request.url.path == "/api/v6/plan"
    assert params["fromPlace"] == "55.842,37.18"
    assert params["toPlace"] == "55.751,37.617"
    assert params["time"] == "2026-07-12T18:40:00+00:00"
    assert params["arriveBy"] == "true"
    assert params["transitModes"] == "SUBURBAN,SUBWAY,BUS"
    assert params["preTransitModes"] == "WALK"
    assert params["postTransitModes"] == "WALK"
    assert params["directModes"] == ""
    assert params["detailedLegs"] == "false"
    assert params["detailedTransfers"] == "false"
    assert params["timetableView"] == "true"
    assert params["numItineraries"] == "3"
    assert params["maxItineraries"] == "3"
    assert request.headers["user-agent"] == "routing-tests/0.1 tests@example.com"
    assert result == {"itineraries": []}


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [400, 404, 500])
async def test_transitous_non_success_preserves_diagnostics(status_code):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            json={"message": "provider rejected request"},
        )

    client = TransitousHttpClient(
        user_agent="routing-tests/0.1 tests@example.com",
        transport=httpx.MockTransport(handler),
        trust_env=False,
    )
    with pytest.raises(TransitousResponseError) as exc_info:
        await client.get("/api/v6/plan")
    await client.aclose()

    assert exc_info.value.status_code == status_code
    assert exc_info.value.response_payload == {
        "message": "provider rejected request"
    }


@pytest.mark.asyncio
async def test_transitous_invalid_json_is_rejected():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    client = TransitousHttpClient(
        user_agent="routing-tests/0.1 tests@example.com",
        transport=httpx.MockTransport(handler),
        trust_env=False,
    )
    with pytest.raises(TransitousInvalidResponseError):
        await client.get("/api/v6/plan")
    await client.aclose()


@pytest.mark.asyncio
async def test_transitous_timeout_is_transport_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = TransitousHttpClient(
        user_agent="routing-tests/0.1 tests@example.com",
        transport=httpx.MockTransport(handler),
        trust_env=False,
    )
    with pytest.raises(TransitousTransportError):
        await client.get("/api/v6/plan")
    await client.aclose()

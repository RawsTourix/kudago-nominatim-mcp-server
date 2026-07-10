import json

import httpx
import pytest

from app.integrations.openrouteservice import (
    OpenRouteServiceConfigurationError,
    OpenRouteServiceHttpClient,
    OpenRouteServiceInvalidResponseError,
    OpenRouteServiceResponseError,
    OpenRouteServiceTransportError,
    directions,
)


@pytest.mark.asyncio
async def test_openrouteservice_directions_keeps_key_in_header_only():
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        return httpx.Response(200, json={"routes": []})

    client = OpenRouteServiceHttpClient(
        api_key="top-secret",
        user_agent="routing-tests/0.1",
        transport=httpx.MockTransport(handler),
        trust_env=False,
    )
    result = await directions(
        client,
        profile="foot-walking",
        coordinates=[[37.18, 55.842], [37.617, 55.751]],
        language="ru",
        instructions=True,
        geometry=False,
    )
    await client.aclose()

    request = seen["request"]
    payload = json.loads(request.content)
    assert request.method == "POST"
    assert request.url.path == "/v2/directions/foot-walking/json"
    assert request.headers["authorization"] == "top-secret"
    assert payload == {
        "coordinates": [[37.18, 55.842], [37.617, 55.751]],
        "instructions": True,
        "geometry": False,
        "language": "ru",
    }
    assert "top-secret" not in request.url.query.decode()
    assert "top-secret" not in request.content.decode()
    assert result == {"routes": []}


@pytest.mark.asyncio
async def test_missing_api_key_is_lazy_configuration_error():
    client = OpenRouteServiceHttpClient(
        api_key="",
        user_agent="routing-tests/0.1",
        transport=httpx.MockTransport(lambda request: httpx.Response(200)),
        trust_env=False,
    )
    with pytest.raises(OpenRouteServiceConfigurationError, match="API_KEY"):
        await client.post("/v2/directions/foot-walking/json", {})
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 403, 404, 429, 500])
async def test_openrouteservice_non_success_preserves_diagnostics(status_code):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            json={"error": {"code": 2009, "message": "route not found"}},
        )

    client = OpenRouteServiceHttpClient(
        api_key="secret",
        user_agent="routing-tests/0.1",
        transport=httpx.MockTransport(handler),
        trust_env=False,
    )
    with pytest.raises(OpenRouteServiceResponseError) as exc_info:
        await client.post("/v2/directions/foot-walking/json", {})
    await client.aclose()

    assert exc_info.value.status_code == status_code
    assert exc_info.value.response_payload["error"]["code"] == 2009
    assert "secret" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_openrouteservice_invalid_json_is_rejected():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    client = OpenRouteServiceHttpClient(
        api_key="secret",
        user_agent="routing-tests/0.1",
        transport=httpx.MockTransport(handler),
        trust_env=False,
    )
    with pytest.raises(OpenRouteServiceInvalidResponseError):
        await client.post("/v2/directions/foot-walking/json", {})
    await client.aclose()


@pytest.mark.asyncio
async def test_openrouteservice_timeout_is_transport_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = OpenRouteServiceHttpClient(
        api_key="secret",
        user_agent="routing-tests/0.1",
        transport=httpx.MockTransport(handler),
        trust_env=False,
    )
    with pytest.raises(OpenRouteServiceTransportError):
        await client.post("/v2/directions/foot-walking/json", {})
    await client.aclose()


@pytest.mark.asyncio
async def test_openrouteservice_redacts_reflected_key_from_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": {"message": "rejected top-secret credential"}},
        )

    client = OpenRouteServiceHttpClient(
        api_key="top-secret",
        user_agent="routing-tests/0.1",
        transport=httpx.MockTransport(handler),
        trust_env=False,
    )
    with pytest.raises(OpenRouteServiceResponseError) as exc_info:
        await client.post("/v2/directions/foot-walking/json", {})
    await client.aclose()

    error = exc_info.value
    assert "top-secret" not in str(error)
    assert "top-secret" not in error.response_text
    assert "top-secret" not in str(error.response_payload)
    assert "[redacted]" in str(error)

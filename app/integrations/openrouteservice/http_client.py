from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class OpenRouteServiceError(Exception):
    """Base exception for OpenRouteService client errors."""


class OpenRouteServiceConfigurationError(OpenRouteServiceError):
    """OpenRouteService cannot be called with the current configuration."""


class OpenRouteServiceParameterError(OpenRouteServiceError):
    """The local OpenRouteService request parameters are invalid."""


class OpenRouteServiceTransportError(OpenRouteServiceError):
    """Network, timeout, DNS, proxy or other transport-level error."""


@dataclass(slots=True)
class OpenRouteServiceResponseError(OpenRouteServiceError):
    """Non-2xx response returned by OpenRouteService."""

    message: str
    status_code: int
    reason_phrase: str
    response_text: str
    response_payload: dict[str, Any] | list[Any] | None

    def __str__(self) -> str:
        return (
            "OpenRouteService returned "
            f"{self.status_code} {self.reason_phrase}: {self.message}"
        )


class OpenRouteServiceInvalidResponseError(OpenRouteServiceError):
    """OpenRouteService returned invalid or unsupported JSON."""


class OpenRouteServiceHttpClient:
    """Small async HTTP client for OpenRouteService directions."""

    DEFAULT_BASE_URL = "https://api.openrouteservice.org/"

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float | httpx.Timeout = 30.0,
        user_agent: str,
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        trust_env: bool = True,
    ) -> None:
        if not user_agent.strip():
            raise OpenRouteServiceParameterError("User-Agent must not be empty")
        self._api_key = api_key.strip() if api_key else None
        self._headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": user_agent,
        }
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            transport=transport,
            trust_env=trust_env,
        )

    async def __aenter__(self) -> OpenRouteServiceHttpClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def close(self) -> None:
        await self.aclose()

    async def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._api_key:
            raise OpenRouteServiceConfigurationError(
                "OPENROUTESERVICE_API_KEY is required to build a street route"
            )
        if not path:
            raise OpenRouteServiceParameterError(
                "OpenRouteService request path is required"
            )

        headers = {**self._headers, "Authorization": self._api_key}
        try:
            response = await self._client.post(
                path,
                json=payload,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise OpenRouteServiceTransportError(
                _redact_text(str(exc) or exc.__class__.__name__, self._api_key)
            ) from exc

        if not response.is_success:
            raise build_response_error(response, secret=self._api_key)

        try:
            data = response.json()
        except ValueError as exc:
            raise OpenRouteServiceInvalidResponseError(
                "OpenRouteService response body is not valid JSON"
            ) from exc
        if not isinstance(data, dict):
            raise OpenRouteServiceInvalidResponseError(
                "OpenRouteService JSON response must be an object"
            )
        return _redact_json(data, self._api_key)


def build_response_error(
    response: httpx.Response,
    *,
    secret: str | None = None,
) -> OpenRouteServiceResponseError:
    response_text = _redact_text(response.text, secret)
    response_payload: dict[str, Any] | list[Any] | None = None
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, (dict, list)):
        response_payload = _redact_json(body, secret)

    message = response_text or response.reason_phrase
    if isinstance(response_payload, dict):
        detail = (
            response_payload.get("error")
            or response_payload.get("message")
            or response_payload.get("detail")
        )
        if isinstance(detail, dict):
            detail = detail.get("message") or detail.get("detail")
        if detail:
            message = str(detail)

    return OpenRouteServiceResponseError(
        message=message,
        status_code=response.status_code,
        reason_phrase=response.reason_phrase,
        response_text=response_text,
        response_payload=response_payload,
    )


def _redact_json(value: Any, secret: str | None) -> Any:
    if not secret:
        return value
    if isinstance(value, dict):
        return {
            key: _redact_json(item, secret)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_json(item, secret) for item in value]
    if isinstance(value, str):
        return _redact_text(value, secret)
    return value


def _redact_text(value: str, secret: str | None) -> str:
    return value.replace(secret, "[redacted]") if secret else value

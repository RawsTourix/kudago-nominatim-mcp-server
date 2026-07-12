from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, TypeAlias

import httpx

JsonData: TypeAlias = dict[str, Any] | list[Any]
ScalarParam: TypeAlias = str | int | float | bool | date | datetime
ParamValue: TypeAlias = ScalarParam | Sequence[ScalarParam] | None
Params: TypeAlias = Mapping[str, ParamValue | Any]


class TransitousError(Exception):
    """Base exception for Transitous client errors."""


class TransitousConfigurationError(TransitousError):
    """Transitous cannot be called with the current configuration."""


class TransitousParameterError(TransitousError):
    """The local Transitous request parameters are invalid."""


class TransitousTransportError(TransitousError):
    """Network, timeout, DNS, proxy or other transport-level error."""


@dataclass(slots=True)
class TransitousResponseError(TransitousError):
    """Non-2xx response returned by Transitous."""

    message: str
    status_code: int
    reason_phrase: str
    response_text: str
    response_payload: dict[str, Any] | list[Any] | None

    def __str__(self) -> str:
        return (
            "Transitous returned "
            f"{self.status_code} {self.reason_phrase}: {self.message}"
        )


class TransitousInvalidResponseError(TransitousError):
    """Transitous returned invalid JSON or an unsupported JSON value."""


class TransitousHttpClient:
    """Small async HTTP client for the public Transitous MOTIS 2 API."""

    DEFAULT_BASE_URL = "https://api.transitous.org/"

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float | httpx.Timeout = 40.0,
        user_agent: str | None,
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        trust_env: bool = True,
    ) -> None:
        if not user_agent or not user_agent.strip():
            raise TransitousConfigurationError(
                "TRANSITOUS_USER_AGENT is required to build a transit route; "
                "include the application name, version and contact"
            )
        user_agent = user_agent.strip()
        if user_agent.lower().startswith("python-httpx"):
            raise TransitousParameterError(
                "Transitous requires an application-specific User-Agent"
            )
        self._headers = {
            "Accept": "application/json",
            "User-Agent": user_agent,
        }
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            transport=transport,
            trust_env=trust_env,
        )

    async def __aenter__(self) -> TransitousHttpClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def close(self) -> None:
        await self.aclose()

    async def get(self, path: str, params: Params | None = None) -> JsonData:
        if not path:
            raise TransitousParameterError("Transitous request path is required")
        try:
            response = await self._client.get(
                path,
                params=prepare_params(params),
                headers=self._headers,
            )
        except httpx.HTTPError as exc:
            raise TransitousTransportError(
                str(exc) or exc.__class__.__name__
            ) from exc

        if not response.is_success:
            raise build_response_error(response)

        try:
            data = response.json()
        except ValueError as exc:
            raise TransitousInvalidResponseError(
                "Transitous response body is not valid JSON"
            ) from exc

        if isinstance(data, (dict, list)):
            return data
        raise TransitousInvalidResponseError(
            "Transitous JSON response must be an object or array"
        )


def prepare_params(params: Params | None) -> dict[str, str]:
    if not params:
        return {}
    prepared: dict[str, str] = {}
    for key, value in params.items():
        encoded = encode_param_value(value)
        if encoded is not None:
            prepared[key] = encoded
    return prepared


def encode_param_value(value: ParamValue | Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (str, int, float)):
        return str(value)
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        items = [encode_param_value(item) for item in value]
        return ",".join(item for item in items if item is not None)
    return str(value)


def build_response_error(response: httpx.Response) -> TransitousResponseError:
    response_text = response.text
    response_payload: dict[str, Any] | list[Any] | None = None
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, (dict, list)):
        response_payload = body

    message = response_text or response.reason_phrase
    if isinstance(body, dict):
        detail = body.get("detail") or body.get("error") or body.get("message")
        if isinstance(detail, dict):
            detail = detail.get("message") or detail.get("detail")
        if detail:
            message = str(detail)

    return TransitousResponseError(
        message=message,
        status_code=response.status_code,
        reason_phrase=response.reason_phrase,
        response_text=response_text,
        response_payload=response_payload,
    )

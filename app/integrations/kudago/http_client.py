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


class KudaGoError(Exception):
    """Base exception for KudaGo client errors."""


class KudaGoTransportError(KudaGoError):
    """Network, timeout, DNS, proxy or other transport-level error."""


@dataclass(slots=True)
class KudaGoResponseError(KudaGoError):
    """Non-2xx response returned by KudaGo API."""

    message: str
    status_code: int
    reason_phrase: str
    response_text: str

    def __str__(self) -> str:
        return f"KudaGo API returned {self.status_code} {self.reason_phrase}: {self.message}"


class KudaGoInvalidResponseError(KudaGoError):
    """The API response body is not valid JSON."""


class KudaGoHttpClient:
    """Small async HTTP client for KudaGo Public API v1.4."""

    DEFAULT_BASE_URL = "https://kudago.com/public-api/v1.4/"

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float | httpx.Timeout = 20.0,
        user_agent: str = "kudago-mcp-client/0.1.0",
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        trust_env: bool = True,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            transport=transport,
            trust_env=trust_env,
            headers={"Accept": "application/json", "User-Agent": user_agent},
        )

    async def __aenter__(self) -> KudaGoHttpClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def get(self, path: str, params: Params | None = None) -> JsonData:
        prepared_params = prepare_params(params)
        try:
            response = await self._client.get(path, params=prepared_params or None)
        except httpx.HTTPError as exc:
            raise KudaGoTransportError(str(exc) or exc.__class__.__name__) from exc

        if not response.is_success:
            raise build_response_error(response)

        try:
            data = response.json()
        except ValueError as exc:
            raise KudaGoInvalidResponseError("KudaGo response body is not valid JSON") from exc

        if isinstance(data, (dict, list)):
            return data
        raise KudaGoInvalidResponseError("KudaGo JSON response must be an object or array")


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
        text = str(value)
        return text if text != "" else None
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        items = [encode_param_value(item) for item in value]
        compact = [item for item in items if item]
        return ",".join(compact) if compact else None
    text = str(value)
    return text if text != "" else None


def build_response_error(response: httpx.Response) -> KudaGoResponseError:
    response_text = response.text
    message = response_text or response.reason_phrase
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        detail = body.get("detail") or body.get("error") or body.get("message")
        if detail:
            message = str(detail)
    return KudaGoResponseError(
        message=message,
        status_code=response.status_code,
        reason_phrase=response.reason_phrase,
        response_text=response_text,
    )

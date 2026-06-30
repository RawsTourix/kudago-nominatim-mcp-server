from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable, Mapping
from typing import Any

import httpx

JsonObject = dict[str, Any]


class NominatimError(Exception):
    """Base error for this package."""


class NominatimParameterError(NominatimError, ValueError):
    """Invalid local parameters before calling Nominatim."""


class NominatimRequestError(NominatimError):
    """Transport/protocol/parsing error around a Nominatim request."""


class NominatimAPIError(NominatimError):
    """Non-2xx response returned by Nominatim."""

    def __init__(self, message: str, *, status_code: int | None = None, reason: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.reason = reason


def comma_join(values: str | int | Iterable[str | int] | None) -> str | None:
    if values is None:
        return None
    if isinstance(values, str):
        value = values.strip()
        return value or None
    if isinstance(values, int):
        return str(values)
    prepared = [str(value).strip() for value in values if str(value).strip()]
    return ",".join(prepared) or None


def bool_int(value: bool | int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    if value in (0, 1):
        return value
    raise NominatimParameterError(f"Expected a bool-like 0/1 value, got {value!r}")


def prepare_params(params: Mapping[str, Any]) -> dict[str, Any]:
    prepared: dict[str, Any] = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue
        if isinstance(value, bool):
            value = 1 if value else 0
        prepared[key] = value
    return prepared


class NominatimHttpClient:
    """Async low-level HTTP client for Nominatim-compatible APIs."""

    DEFAULT_BASE_URL = "https://nominatim.openstreetmap.org/"

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float | httpx.Timeout = 20.0,
        user_agent: str = "nominatim-geo-client/0.1.0",
        referer: str | None = None,
        min_interval_seconds: float = 1.0,
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        trust_env: bool = True,
    ) -> None:
        if not user_agent or user_agent.startswith(("python-httpx", "httpx")):
            raise NominatimParameterError("Nominatim requires a real application User-Agent, not a stock HTTP client one.")
        self.min_interval_seconds = min_interval_seconds
        self._last_request_at = 0.0
        self._rate_lock = asyncio.Lock()
        self._owns_client = client is None
        headers = {"Accept": "application/json", "User-Agent": user_agent}
        if referer:
            headers["Referer"] = referer
        self._client = client or httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            transport=transport,
            headers=headers,
            trust_env=trust_env,
        )

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> NominatimHttpClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def _respect_rate_limit(self) -> None:
        if self.min_interval_seconds <= 0:
            return
        async with self._rate_lock:
            now = time.monotonic()
            wait_for = self._last_request_at + self.min_interval_seconds - now
            if wait_for > 0:
                await asyncio.sleep(wait_for)
            self._last_request_at = time.monotonic()

    async def get(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        prepared = prepare_params(params or {})
        await self._respect_rate_limit()
        try:
            response = await self._client.get(path, params=prepared or None)
        except httpx.HTTPError as exc:
            detail = str(exc) or exc.__class__.__name__
            raise NominatimRequestError(f"Nominatim request failed: {exc.__class__.__name__}: {detail}; request={path!r}; params={prepared!r}") from exc
        if response.is_success:
            if not response.content:
                return None
            try:
                return response.json()
            except ValueError as exc:
                raise NominatimRequestError("Expected JSON response from Nominatim") from exc
        message = response.text or response.reason_phrase
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict):
            detail = body.get("error") or body.get("message") or body.get("detail")
            if detail:
                message = str(detail)
        raise NominatimAPIError(message, status_code=response.status_code, reason=response.reason_phrase)

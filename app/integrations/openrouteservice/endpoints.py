from typing import Any
from urllib.parse import quote

from .http_client import OpenRouteServiceHttpClient


async def directions(
    client: OpenRouteServiceHttpClient,
    *,
    profile: str,
    coordinates: list[list[float]],
    language: str | None,
    instructions: bool,
    geometry: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "coordinates": coordinates,
        "instructions": instructions,
        "geometry": geometry,
    }
    if language is not None:
        payload["language"] = language
    return await client.post(
        f"/v2/directions/{quote(profile, safe='')}/json",
        payload,
    )

import time
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.integrations.openrouteservice import (
    OpenRouteServiceHttpClient,
    OpenRouteServiceInvalidResponseError,
    OpenRouteServiceResponseError,
    directions,
)
from app.repositories.upstream_call_repository import UpstreamCallRepository
from app.schemas.routing import StreetRouteProfile, StreetRouteRequest


PROFILE_MAP = {
    StreetRouteProfile.WALKING: "foot-walking",
    StreetRouteProfile.CYCLING: "cycling-regular",
    StreetRouteProfile.DRIVING: "driving-car",
}
NO_ROUTE_CODES = {2009, 2016}


class StreetRoutingService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        client: OpenRouteServiceHttpClient | None = None,
    ) -> None:
        self.upstream_call_repo = UpstreamCallRepository(session)
        self.client = client

    async def plan_route(
        self,
        *,
        job_id: UUID,
        request: StreetRouteRequest,
    ) -> dict[str, Any]:
        provider_profile = PROFILE_MAP[request.profile]
        coordinates = [
            [request.origin_lon, request.origin_lat],
            [request.destination_lon, request.destination_lat],
        ]
        url_path = f"/v2/directions/{provider_profile}/json"
        request_payload = {
            "profile": request.profile.value,
            "coordinates": coordinates,
            "language": request.language,
            "instructions": request.include_instructions,
            "geometry": request.include_geometry,
        }
        client = self.client or OpenRouteServiceHttpClient(
            api_key=settings.openrouteservice_api_key,
            base_url=settings.openrouteservice_base_url,
            timeout=settings.openrouteservice_timeout_seconds,
            user_agent=settings.openrouteservice_user_agent,
            trust_env=True,
        )
        started = time.perf_counter()

        try:
            raw = await directions(
                client,
                profile=provider_profile,
                coordinates=coordinates,
                language=request.language,
                instructions=request.include_instructions,
                geometry=request.include_geometry,
            )
        except Exception as exc:
            response_payload = (
                exc.response_payload
                if isinstance(exc, OpenRouteServiceResponseError)
                else None
            )
            await self.upstream_call_repo.create(
                job_id=job_id,
                provider="openrouteservice",
                operation="directions",
                url_path=url_path,
                request_payload=request_payload,
                response_payload=response_payload,
                response_status_code=(
                    exc.status_code
                    if isinstance(exc, OpenRouteServiceResponseError)
                    else None
                ),
                duration_ms=_duration_ms(started),
                success=False,
                error_type=exc.__class__.__name__,
                error_message=_safe_error_message(
                    exc,
                    getattr(client, "_api_key", None)
                    or settings.openrouteservice_api_key,
                ),
            )
            if isinstance(exc, OpenRouteServiceResponseError) and (
                _is_no_route_error(exc)
            ):
                return _no_route_result(request)
            raise
        finally:
            if self.client is None:
                await client.aclose()

        try:
            result = self._normalize(raw, request)
        except Exception as exc:
            await self.upstream_call_repo.create(
                job_id=job_id,
                provider="openrouteservice",
                operation="directions",
                url_path=url_path,
                request_payload=request_payload,
                response_payload=raw,
                response_status_code=200,
                duration_ms=_duration_ms(started),
                success=False,
                error_type=exc.__class__.__name__,
                error_message=_safe_error_message(
                    exc,
                    getattr(client, "_api_key", None)
                    or settings.openrouteservice_api_key,
                ),
            )
            raise

        await self.upstream_call_repo.create(
            job_id=job_id,
            provider="openrouteservice",
            operation="directions",
            url_path=url_path,
            request_payload=request_payload,
            response_payload=raw,
            response_status_code=200,
            duration_ms=_duration_ms(started),
            success=True,
        )
        return result

    @staticmethod
    def _normalize(
        raw: dict[str, Any],
        request: StreetRouteRequest,
    ) -> dict[str, Any]:
        error_code = _provider_error_code(raw)
        if error_code in NO_ROUTE_CODES:
            return _no_route_result(request)
        if raw.get("error") is not None:
            raise OpenRouteServiceInvalidResponseError(
                "OpenRouteService returned an unexpected error object"
            )

        raw_routes = raw.get("routes")
        if not isinstance(raw_routes, list):
            raise OpenRouteServiceInvalidResponseError(
                "OpenRouteService response does not contain a routes array"
            )
        if not raw_routes:
            return _no_route_result(request)
        if not all(isinstance(route, dict) for route in raw_routes):
            raise OpenRouteServiceInvalidResponseError(
                "OpenRouteService routes must be JSON objects"
            )

        routes = [
            _normalize_route(route, raw, request)
            for route in raw_routes
        ]
        metadata = raw.get("metadata")
        attribution = (
            _normalize_attribution(metadata.get("attribution"))
            if isinstance(metadata, dict)
            else []
        )
        return {
            "status": "ok",
            "provider": "openrouteservice",
            "profile": request.profile.value,
            "query": _street_query(request),
            "returned": len(routes),
            "routes": routes,
            "warnings": _list_value(raw.get("warnings")),
            "attribution": attribution,
        }


def _normalize_route(
    route: dict[str, Any],
    raw: dict[str, Any],
    request: StreetRouteRequest,
) -> dict[str, Any]:
    summary = route.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    raw_segments = route.get("segments")
    raw_segments = raw_segments if isinstance(raw_segments, list) else []
    if not all(isinstance(segment, dict) for segment in raw_segments):
        raise OpenRouteServiceInvalidResponseError(
            "OpenRouteService segments must be JSON objects"
        )
    bbox = route.get("bbox")
    if not isinstance(bbox, list):
        bbox = raw.get("bbox") if isinstance(raw.get("bbox"), list) else None

    return {
        "distance_meters": _number(summary.get("distance")),
        "duration_seconds": _number(summary.get("duration")),
        "bbox": bbox,
        "segments": [
            _normalize_segment(segment, request.include_instructions)
            for segment in raw_segments
        ],
        "geometry": route.get("geometry") if request.include_geometry else None,
    }


def _normalize_segment(
    segment: dict[str, Any],
    include_instructions: bool,
) -> dict[str, Any]:
    raw_steps = segment.get("steps") if include_instructions else []
    raw_steps = raw_steps if isinstance(raw_steps, list) else []
    if not all(isinstance(step, dict) for step in raw_steps):
        raise OpenRouteServiceInvalidResponseError(
            "OpenRouteService steps must be JSON objects"
        )
    return {
        "distance_meters": _number(segment.get("distance")),
        "duration_seconds": _number(segment.get("duration")),
        "steps": [
            {
                "instruction": _text(step.get("instruction")),
                "name": _text(step.get("name")),
                "distance_meters": _number(step.get("distance")),
                "duration_seconds": _number(step.get("duration")),
                "type": _integer(step.get("type")),
            }
            for step in raw_steps
        ],
    }


def _no_route_result(request: StreetRouteRequest) -> dict[str, Any]:
    return {
        "status": "no_route",
        "provider": "openrouteservice",
        "profile": request.profile.value,
        "query": _street_query(request),
        "returned": 0,
        "routes": [],
        "message": (
            "No street route was found for the selected points and profile."
        ),
        "warnings": [],
        "attribution": [],
    }


def _street_query(request: StreetRouteRequest) -> dict[str, Any]:
    return {
        "origin": {"lat": request.origin_lat, "lon": request.origin_lon},
        "destination": {
            "lat": request.destination_lat,
            "lon": request.destination_lon,
        },
    }


def _is_no_route_error(exc: OpenRouteServiceResponseError) -> bool:
    if exc.status_code == 404:
        return True
    return exc.status_code in {400, 422} and _provider_error_code(
        exc.response_payload
    ) in NO_ROUTE_CODES


def _provider_error_code(payload: Any) -> int | None:
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if isinstance(error, dict):
        code = error.get("code")
    else:
        code = payload.get("code")
    return code if isinstance(code, int) else None


def _normalize_attribution(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, str):
        return [{"name": value}]
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, str):
            result.append({"name": item})
        elif isinstance(item, dict):
            compact = {
                key: item[key]
                for key in ("name", "url")
                if key in item
            }
            if compact:
                result.append(compact)
    return result


def _safe_error_message(exc: Exception, secret: str | None) -> str:
    message = str(exc)
    if secret:
        message = message.replace(secret, "[redacted]")
    return message


def _duration_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _integer(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None

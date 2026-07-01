import time
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.nominatim import NominatimHttpClient, search
from app.repositories.geo_cache_repository import GeoCacheRepository
from app.repositories.upstream_call_repository import UpstreamCallRepository


class GeoService:
    def __init__(self, session: AsyncSession):
        self.geo_cache_repo = GeoCacheRepository(session)
        self.upstream_call_repo = UpstreamCallRepository(session)

    async def resolve_place(
        self,
        *,
        job_id: UUID,
        query: str,
        countrycodes: str | None = "ru",
        limit: int = 5,
        accept_language: str | None = "ru",
    ) -> dict[str, Any]:
        cached = await self.geo_cache_repo.get_valid(
            query=query,
            countrycodes=countrycodes,
            accept_language=accept_language,
        )

        if cached is not None:
            return {
                "status": cached.status,
                "source": "cache",
                "query": query,
                "candidates": cached.candidates,
                "selected_lat": (
                    float(cached.selected_lat)
                    if cached.selected_lat is not None
                    else None
                ),
                "selected_lon": (
                    float(cached.selected_lon)
                    if cached.selected_lon is not None
                    else None
                ),
                "radius": cached.radius,
            }

        started = time.perf_counter()
        request_payload = {
            "q": query,
            "countrycodes": countrycodes,
            "limit": limit,
            "accept_language": accept_language,
        }
        client = NominatimHttpClient(
            user_agent="kudago-fastapi-service/0.1.0",
            min_interval_seconds=1.0,
            trust_env=True,
        )

        try:
            data = await search(
                client,
                q=query,
                countrycodes=countrycodes,
                limit=limit,
                accept_language=accept_language,
                addressdetails=True,
                namedetails=True,
                extratags=True,
            )
            duration_ms = int((time.perf_counter() - started) * 1000)

            await self.upstream_call_repo.create(
                job_id=job_id,
                provider="nominatim",
                operation="search",
                url_path="/search",
                request_payload=request_payload,
                response_payload=data,
                response_status_code=200,
                duration_ms=duration_ms,
                success=True,
            )

            candidates = data if isinstance(data, list) else []
            if not candidates:
                status = "not_found"
                selected_lat = None
                selected_lon = None
                radius = None
            elif len(candidates) == 1:
                status = "ok"
                selected_lat = float(candidates[0]["lat"])
                selected_lon = float(candidates[0]["lon"])
                radius = 50_000
            else:
                status = "ambiguous"
                selected_lat = None
                selected_lon = None
                radius = None

            await self.geo_cache_repo.create(
                query=query,
                countrycodes=countrycodes,
                accept_language=accept_language,
                status=status,
                candidates=candidates,
                selected_lat=selected_lat,
                selected_lon=selected_lon,
                radius=radius,
            )

            return {
                "status": status,
                "source": "nominatim",
                "query": query,
                "candidates": candidates,
                "selected_lat": selected_lat,
                "selected_lon": selected_lon,
                "radius": radius,
            }
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            await self.upstream_call_repo.create(
                job_id=job_id,
                provider="nominatim",
                operation="search",
                url_path="/search",
                request_payload=request_payload,
                response_payload=None,
                response_status_code=None,
                duration_ms=duration_ms,
                success=False,
                error_type=exc.__class__.__name__,
                error_message=str(exc),
            )
            raise
        finally:
            await client.close()

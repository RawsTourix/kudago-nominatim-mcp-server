from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.geo_cache import GeoCache


def normalize_geo_query(value: str) -> str:
    return " ".join(value.casefold().replace("ё", "е").split())


class GeoCacheRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_valid(
        self,
        *,
        query: str,
        countrycodes: str | None,
        accept_language: str | None,
    ) -> GeoCache | None:
        normalized_query = normalize_geo_query(query)
        now = datetime.now(timezone.utc)

        result = await self.session.execute(
            select(GeoCache).where(
                GeoCache.normalized_query == normalized_query,
                GeoCache.countrycodes == countrycodes,
                GeoCache.accept_language == accept_language,
                (GeoCache.expires_at.is_(None)) | (GeoCache.expires_at > now),
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        query: str,
        countrycodes: str | None,
        accept_language: str | None,
        status: str,
        candidates: list[dict[str, Any]],
        selected_lat: float | None = None,
        selected_lon: float | None = None,
        radius: int | None = None,
        ttl_hours: int = 24,
    ) -> GeoCache:
        cache = GeoCache(
            query=query,
            normalized_query=normalize_geo_query(query),
            countrycodes=countrycodes,
            accept_language=accept_language,
            status=status,
            candidates=candidates,
            selected_lat=selected_lat,
            selected_lon=selected_lon,
            radius=radius,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=ttl_hours),
        )
        self.session.add(cache)
        await self.session.flush()
        return cache

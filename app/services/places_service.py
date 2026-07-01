import time
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.integrations.kudago import KudaGoHttpClient
from app.integrations.kudago import places as kudago_places
from app.repositories.upstream_call_repository import UpstreamCallRepository


def csv_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def kudago_has_showings(value: bool | str | None) -> str | None:
    if value is None:
        return None

    if isinstance(value, bool):
        return "movie" if value else None

    value = value.strip().lower()
    if not value:
        return None

    if value == "movie":
        return "movie"

    raise ValueError("has_showings for KudaGo places must be true or 'movie'")


class PlacesService:
    def __init__(self, session: AsyncSession):
        self.upstream_call_repo = UpstreamCallRepository(session)

    def create_client(self) -> KudaGoHttpClient:
        return KudaGoHttpClient(
            base_url=settings.kudago_base_url,
            user_agent=settings.kudago_user_agent,
            trust_env=True,
        )

    async def search_places(
        self,
        *,
        job_id: UUID,
        location: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        radius: int | None = None,
        categories: str | None = None,
        tags: str | None = None,
        has_showings: bool | None = None,
        showing_since: str | int | None = None,
        showing_until: str | int | None = None,
        page: int = 1,
        page_size: int = 10,
        lang: str = "ru",
    ) -> dict[str, Any]:
        client = self.create_client()
        started = time.perf_counter()
        fields = (
            "id,title,slug,address,phone,site_url,subway,coords,location,"
            "categories,tags,images"
        )
        has_showings_param = kudago_has_showings(has_showings)
        request_payload = {
            "lang": lang,
            "page": page,
            "page_size": page_size,
            "fields": fields,
            "expand": "location,categories",
            "text_format": "text",
            "location": location,
            "has_showings": has_showings_param,
            "showing_since": showing_since,
            "showing_until": showing_until,
            "categories": categories,
            "tags": tags,
            "lat": lat,
            "lon": lon,
            "radius": radius,
        }

        try:
            data = await kudago_places(
                client,
                lang=lang,
                page=page,
                page_size=page_size,
                fields=fields,
                expand="location,categories",
                text_format="text",
                location=location,
                has_showings=has_showings_param,
                showing_since=showing_since,
                showing_until=showing_until,
                categories=csv_or_none(categories),
                tags=csv_or_none(tags),
                lat=lat,
                lon=lon,
                radius=radius,
            )
            duration_ms = int((time.perf_counter() - started) * 1000)
            await self.upstream_call_repo.create(
                job_id=job_id,
                provider="kudago",
                operation="places",
                url_path="/places/",
                request_payload=request_payload,
                response_payload=data,
                response_status_code=200,
                duration_ms=duration_ms,
                success=True,
            )

            results = data.get("results", []) if isinstance(data, dict) else []
            count = data.get("count") if isinstance(data, dict) else None
            return {
                "status": "ok",
                "source": "kudago",
                "count": count,
                "returned": len(results),
                "items": results,
                "raw": data,
            }
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            await self.upstream_call_repo.create(
                job_id=job_id,
                provider="kudago",
                operation="places",
                url_path="/places/",
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
            await client.aclose()

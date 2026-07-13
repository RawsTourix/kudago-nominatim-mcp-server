import time
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.integrations.kudago import KudaGoHttpClient
from app.integrations.kudago import events as kudago_events
from app.integrations.kudago import locations as kudago_locations
from app.repositories.upstream_call_repository import UpstreamCallRepository


EVENT_SEARCH_FIELDS = (
    "id,title,short_title,description,dates,place,location,categories,tags,"
    "price,is_free,site_url,age_restriction"
)


def normalize_text(value: str) -> str:
    return " ".join(value.casefold().replace("ё", "е").split())


def csv_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


class EventsService:
    def __init__(self, session: AsyncSession):
        self.upstream_call_repo = UpstreamCallRepository(session)

    def create_client(self) -> KudaGoHttpClient:
        return KudaGoHttpClient(
            base_url=settings.kudago_base_url,
            user_agent=settings.kudago_user_agent,
            trust_env=True,
        )

    async def find_kudago_location(
        self,
        *,
        job_id: UUID,
        place_query: str,
        lang: str = "ru",
    ) -> dict[str, Any] | None:
        client = self.create_client()
        started = time.perf_counter()
        request_payload = {
            "lang": lang,
            "fields": ["slug", "name", "timezone", "coords"],
        }

        try:
            data = await kudago_locations(
                client,
                lang=lang,
                fields=["slug", "name", "timezone", "coords"],
            )
            duration_ms = int((time.perf_counter() - started) * 1000)
            await self.upstream_call_repo.create(
                job_id=job_id,
                provider="kudago",
                operation="locations",
                url_path="/locations/",
                request_payload=request_payload,
                response_payload=data,
                response_status_code=200,
                duration_ms=duration_ms,
                success=True,
            )

            items = (
                data
                if isinstance(data, list)
                else data.get("results", [])
                if isinstance(data, dict)
                else []
            )
            needle = normalize_text(place_query)
            for item in items:
                if not isinstance(item, dict):
                    continue
                slug = str(item.get("slug") or "")
                name = str(item.get("name") or "")
                if normalize_text(slug) == needle or normalize_text(name) == needle:
                    return item
            return None
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            await self.upstream_call_repo.create(
                job_id=job_id,
                provider="kudago",
                operation="locations",
                url_path="/locations/",
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

    async def search_events(
        self,
        *,
        job_id: UUID,
        location: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        radius: int | None = None,
        actual_since: str | int | None = None,
        actual_until: str | int | None = None,
        categories: str | None = None,
        tags: str | None = None,
        is_free: bool | None = None,
        page: int = 1,
        page_size: int = 10,
        lang: str = "ru",
    ) -> dict[str, Any]:
        client = self.create_client()
        started = time.perf_counter()
        fields = EVENT_SEARCH_FIELDS
        request_payload = {
            "lang": lang,
            "page": page,
            "page_size": page_size,
            "fields": fields,
            "expand": "dates,place,location",
            "order_by": "-publication_date",
            "text_format": "text",
            "location": location,
            "actual_since": actual_since,
            "actual_until": actual_until,
            "is_free": is_free,
            "categories": categories,
            "tags": tags,
            "lat": lat,
            "lon": lon,
            "radius": radius,
        }

        try:
            data = await kudago_events(
                client,
                lang=lang,
                page=page,
                page_size=page_size,
                fields=fields,
                expand="dates,place,location",
                order_by="-publication_date",
                text_format="text",
                location=location,
                actual_since=actual_since,
                actual_until=actual_until,
                is_free=is_free,
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
                operation="events",
                url_path="/events/",
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
                operation="events",
                url_path="/events/",
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

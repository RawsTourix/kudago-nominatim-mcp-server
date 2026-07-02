import time
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.integrations.kudago import KudaGoHttpClient
from app.integrations.kudago import movies as kudago_movies
from app.repositories.upstream_call_repository import UpstreamCallRepository


def csv_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def bool_param(value: bool | None) -> str | None:
    if value is None:
        return None
    return "true" if value else "false"


class MoviesService:
    def __init__(self, session: AsyncSession):
        self.upstream_call_repo = UpstreamCallRepository(session)

    def create_client(self) -> KudaGoHttpClient:
        return KudaGoHttpClient(
            base_url=settings.kudago_base_url,
            user_agent=settings.kudago_user_agent,
            trust_env=True,
        )

    async def search_movies(
        self,
        *,
        job_id: UUID,
        location: str | None = None,
        place_id: int | None = None,
        tags: str | None = None,
        is_free: bool | None = None,
        premiering_in_location: bool | None = None,
        actual_since: str | int | None = None,
        actual_until: str | int | None = None,
        page: int = 1,
        page_size: int = 10,
        lang: str = "ru",
    ) -> dict[str, Any]:
        client = self.create_client()
        started = time.perf_counter()
        fields = (
            "id,title,original_title,description,body_text,poster,site_url,"
            "genres,country,year,running_time,age_restriction"
        )
        request_payload = {
            "lang": lang,
            "page": page,
            "page_size": page_size,
            "fields": fields,
            "expand": None,
            "order_by": None,
            "text_format": "text",
            "tags": tags,
            "location": location,
            "premiering_in_location": premiering_in_location,
            "is_free": is_free,
            "place": place_id,
            "actual_since": actual_since,
            "actual_until": actual_until,
        }

        try:
            data = await kudago_movies(
                client,
                lang=lang,
                page=page,
                page_size=page_size,
                fields=fields,
                text_format="text",
                tags=csv_or_none(tags),
                location=location,
                premiering_in_location=bool_param(premiering_in_location),
                is_free=bool_param(is_free),
                place=place_id,
                actual_since=actual_since,
                actual_until=actual_until,
            )
            duration_ms = int((time.perf_counter() - started) * 1000)
            await self.upstream_call_repo.create(
                job_id=job_id,
                provider="kudago",
                operation="movies",
                url_path="/movies/",
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
                operation="movies",
                url_path="/movies/",
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

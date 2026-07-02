import time
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.integrations.kudago import KudaGoHttpClient
from app.integrations.kudago import movie_showings as kudago_movie_showings
from app.integrations.kudago import movie_showings_for_movie
from app.repositories.upstream_call_repository import UpstreamCallRepository


def bool_param(value: bool | None) -> str | None:
    if value is None:
        return None
    return "true" if value else "false"


class MovieShowingsService:
    def __init__(self, session: AsyncSession):
        self.upstream_call_repo = UpstreamCallRepository(session)

    def create_client(self) -> KudaGoHttpClient:
        return KudaGoHttpClient(
            base_url=settings.kudago_base_url,
            user_agent=settings.kudago_user_agent,
            trust_env=True,
        )

    async def search_movie_showings(
        self,
        *,
        job_id: UUID,
        movie_id: int | None = None,
        location: str | None = None,
        actual_since: str | int | None = None,
        actual_until: str | int | None = None,
        place_id: int | None = None,
        is_free: bool | None = None,
        page: int = 1,
        page_size: int = 10,
        lang: str = "ru",
    ) -> dict[str, Any]:
        client = self.create_client()
        started = time.perf_counter()
        fields = (
            "id,movie,place,datetime,three_d,imax,four_dx,"
            "original_language,price"
        )
        request_payload = {
            "movie_id": movie_id,
            "lang": lang,
            "page": page,
            "page_size": page_size,
            "fields": fields,
            "expand": "movie,place",
            "location": location,
            "actual_since": actual_since,
            "actual_until": actual_until,
            "place_id": place_id,
            "is_free": is_free,
        }

        operation = (
            "movie_showings_for_movie"
            if movie_id is not None
            else "movie_showings"
        )
        url_path = (
            f"/movies/{movie_id}/showings/"
            if movie_id is not None
            else "/movie-showings/"
        )

        try:
            if movie_id is not None:
                data = await movie_showings_for_movie(
                    client,
                    movie_id,
                    lang=lang,
                    page=page,
                    page_size=page_size,
                    fields=fields,
                    expand="movie,place",
                    location=location,
                    actual_since=actual_since,
                    actual_until=actual_until,
                    place=place_id,
                    is_free=bool_param(is_free),
                )
            else:
                data = await kudago_movie_showings(
                    client,
                    lang=lang,
                    page=page,
                    page_size=page_size,
                    fields=fields,
                    expand="movie,place",
                    location=location,
                    actual_since=actual_since,
                    actual_until=actual_until,
                    place_id=place_id,
                    is_free=bool_param(is_free),
                )

            duration_ms = int((time.perf_counter() - started) * 1000)
            await self.upstream_call_repo.create(
                job_id=job_id,
                provider="kudago",
                operation=operation,
                url_path=url_path,
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
                operation=operation,
                url_path=url_path,
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

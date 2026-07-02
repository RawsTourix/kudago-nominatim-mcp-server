import time
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.integrations.kudago import KudaGoHttpClient
from app.integrations.kudago import lists as kudago_lists
from app.repositories.upstream_call_repository import UpstreamCallRepository


def csv_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


class ListsService:
    def __init__(self, session: AsyncSession):
        self.upstream_call_repo = UpstreamCallRepository(session)

    def create_client(self) -> KudaGoHttpClient:
        return KudaGoHttpClient(
            base_url=settings.kudago_base_url,
            user_agent=settings.kudago_user_agent,
            trust_env=True,
        )

    async def search_lists(
        self,
        *,
        job_id: UUID,
        location: str | None = None,
        tags: str | None = None,
        page: int = 1,
        page_size: int = 10,
        lang: str = "ru",
    ) -> dict[str, Any]:
        client = self.create_client()
        started = time.perf_counter()
        fields = (
            "id,title,publication_date,description,site_url,"
            "favorites_count,comments_count"
        )
        request_payload = {
            "lang": lang,
            "page": page,
            "page_size": page_size,
            "fields": fields,
            "expand": None,
            "order_by": "-publication_date",
            "text_format": "text",
            "tags": tags,
            "location": location,
        }

        try:
            data = await kudago_lists(
                client,
                lang=lang,
                page=page,
                page_size=page_size,
                fields=fields,
                order_by="-publication_date",
                text_format="text",
                tags=csv_or_none(tags),
                location=location,
            )
            duration_ms = int((time.perf_counter() - started) * 1000)
            await self.upstream_call_repo.create(
                job_id=job_id,
                provider="kudago",
                operation="lists",
                url_path="/lists/",
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
                operation="lists",
                url_path="/lists/",
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

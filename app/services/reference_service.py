from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.integrations.kudago import (
    KudaGoHttpClient,
    event_categories,
    location,
    locations,
    place_categories,
)
from app.repositories.upstream_call_repository import UpstreamCallRepository
from app.services.tracked_kudago_client import TrackedKudaGoHttpClient


class ReferenceService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.upstream_call_repo = UpstreamCallRepository(session)

    def create_client(self, *, job_id: UUID | None = None) -> KudaGoHttpClient:
        if job_id is not None:
            return TrackedKudaGoHttpClient(
                job_id=job_id,
                upstream_call_repo=self.upstream_call_repo,
                operation_prefix="reference",
                base_url=settings.kudago_base_url,
                user_agent=settings.kudago_user_agent,
                trust_env=True,
            )
        return KudaGoHttpClient(
            base_url=settings.kudago_base_url,
            user_agent=settings.kudago_user_agent,
            trust_env=True,
        )

    async def get_event_categories(
        self,
        *,
        lang: str = "ru",
        job_id: UUID | None = None,
    ) -> dict[str, Any]:
        client = self.create_client(job_id=job_id)
        try:
            data = await event_categories(client, lang=lang)
            return {
                "status": "ok",
                "kind": "event_categories",
                "data": data,
            }
        finally:
            await client.aclose()

    async def get_place_categories(
        self,
        *,
        lang: str = "ru",
        job_id: UUID | None = None,
    ) -> dict[str, Any]:
        client = self.create_client(job_id=job_id)
        try:
            data = await place_categories(client, lang=lang)
            return {
                "status": "ok",
                "kind": "place_categories",
                "data": data,
            }
        finally:
            await client.aclose()

    async def get_locations(
        self,
        *,
        lang: str = "ru",
        job_id: UUID | None = None,
    ) -> dict[str, Any]:
        client = self.create_client(job_id=job_id)
        try:
            data = await locations(
                client,
                lang=lang,
                fields=[
                    "slug",
                    "name",
                    "timezone",
                    "coords",
                    "language",
                    "currency",
                ],
            )
            return {
                "status": "ok",
                "kind": "locations",
                "data": data,
            }
        finally:
            await client.aclose()

    async def get_location(
        self,
        *,
        slug: str,
        lang: str = "ru",
        job_id: UUID | None = None,
    ) -> dict[str, Any]:
        client = self.create_client(job_id=job_id)
        try:
            data = await location(client, slug, lang=lang)
            return {
                "status": "ok",
                "kind": "location",
                "slug": slug,
                "data": data,
            }
        finally:
            await client.aclose()

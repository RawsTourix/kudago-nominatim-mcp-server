from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.integrations.kudago import (
    KudaGoHttpClient,
    event_categories,
    location,
    locations,
    place_categories,
)


class ReferenceService:
    def __init__(self, session: AsyncSession):
        self.session = session

    def create_client(self) -> KudaGoHttpClient:
        return KudaGoHttpClient(
            base_url=settings.kudago_base_url,
            user_agent=settings.kudago_user_agent,
            trust_env=True,
        )

    async def get_event_categories(self, *, lang: str = "ru") -> dict[str, Any]:
        client = self.create_client()
        try:
            data = await event_categories(client, lang=lang)
            return {
                "status": "ok",
                "kind": "event_categories",
                "data": data,
            }
        finally:
            await client.aclose()

    async def get_place_categories(self, *, lang: str = "ru") -> dict[str, Any]:
        client = self.create_client()
        try:
            data = await place_categories(client, lang=lang)
            return {
                "status": "ok",
                "kind": "place_categories",
                "data": data,
            }
        finally:
            await client.aclose()

    async def get_locations(self, *, lang: str = "ru") -> dict[str, Any]:
        client = self.create_client()
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
    ) -> dict[str, Any]:
        client = self.create_client()
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

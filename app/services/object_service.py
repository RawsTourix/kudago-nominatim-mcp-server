from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.integrations.kudago import (
    KudaGoHttpClient,
    agent_detail,
    agent_role_detail,
    event,
    event_comments,
    list_comments,
    list_detail,
    location,
    movie_comments,
    movie_detail,
    movie_showing_detail,
    movie_showings_for_movie,
    news_comments,
    news_detail,
    place_comments,
    place_detail,
)


class ObjectService:
    def __init__(self, session: AsyncSession):
        self.session = session

    def create_client(self) -> KudaGoHttpClient:
        return KudaGoHttpClient(
            base_url=settings.kudago_base_url,
            user_agent=settings.kudago_user_agent,
            trust_env=True,
        )

    async def get_object_detail(
        self,
        *,
        object_type: str,
        object_id: str,
        include_comments: bool = False,
        include_showings: bool = False,
        lang: str = "ru",
    ) -> dict[str, Any]:
        kind = object_type.strip().lower()
        client = self.create_client()

        try:
            result: dict[str, Any] = {
                "status": "ok",
                "object_type": kind,
                "object_id": str(object_id),
                "data": None,
                "comments": None,
                "showings": None,
            }

            if kind == "event":
                parsed_id = int(object_id)
                result["data"] = await event(
                    client,
                    parsed_id,
                    lang=lang,
                    expand="dates,place,location",
                )
                if include_comments:
                    result["comments"] = await event_comments(
                        client,
                        parsed_id,
                        lang=lang,
                    )
                return result

            if kind == "place":
                parsed_id = int(object_id)
                result["data"] = await place_detail(client, parsed_id, lang=lang)
                if include_comments:
                    result["comments"] = await place_comments(
                        client,
                        parsed_id,
                        lang=lang,
                    )
                return result

            if kind == "movie":
                parsed_id = int(object_id)
                result["data"] = await movie_detail(client, parsed_id, lang=lang)
                if include_comments:
                    result["comments"] = await movie_comments(
                        client,
                        parsed_id,
                        lang=lang,
                    )
                if include_showings:
                    result["showings"] = await movie_showings_for_movie(
                        client,
                        parsed_id,
                        lang=lang,
                        page=1,
                        page_size=20,
                        expand="movie,place",
                    )
                return result

            if kind == "movie_showing":
                parsed_id = int(object_id)
                result["data"] = await movie_showing_detail(
                    client,
                    parsed_id,
                    lang=lang,
                )
                return result

            if kind == "news":
                parsed_id = int(object_id)
                result["data"] = await news_detail(client, parsed_id, lang=lang)
                if include_comments:
                    result["comments"] = await news_comments(
                        client,
                        parsed_id,
                        lang=lang,
                    )
                return result

            if kind == "list":
                parsed_id = int(object_id)
                result["data"] = await list_detail(client, parsed_id, lang=lang)
                if include_comments:
                    result["comments"] = await list_comments(
                        client,
                        parsed_id,
                        lang=lang,
                    )
                return result

            if kind == "agent":
                parsed_id = int(object_id)
                result["data"] = await agent_detail(
                    client,
                    parsed_id,
                    lang=lang,
                    text_format="text",
                )
                return result

            if kind == "agent_role":
                parsed_id = int(object_id)
                result["data"] = await agent_role_detail(
                    client,
                    parsed_id,
                    lang=lang,
                )
                return result

            if kind == "location":
                result["data"] = await location(client, object_id, lang=lang)
                return result

            raise ValueError(
                "object_type must be "
                "event|place|movie|movie_showing|news|list|agent|agent_role|location"
            )
        finally:
            await client.aclose()

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from pydantic import ValidationError

from app.mcp.executor import run_mcp_command
from app.mcp.mappers import city_payload
from app.mcp.schemas.common import (
    CityInput,
    LocationSlugInput,
    PageInput,
    SearchLimitInput,
)
from app.mcp.schemas.discovery import (
    FindCityGuidesInput,
    FindCityNewsInput,
    OnlyCurrentInput,
)
from app.mcp.serializers import serialize_guides, serialize_news
from app.mcp.tools._common import (
    MCP_FACADE_VERSION,
    READ_ONLY_TOOL_ANNOTATIONS,
    validation_error,
)
from app.schemas.lists import ListsSearchRequest
from app.schemas.news import NewsSearchRequest


def register_content_tools(mcp: FastMCP) -> None:
    @mcp.tool(
        name="find_city_news",
        annotations=READ_ONLY_TOOL_ANNOTATIONS,
        version=MCP_FACADE_VERSION,
    )
    async def find_city_news(
        city: CityInput = None,
        location_slug: LocationSlugInput = None,
        only_current: OnlyCurrentInput = True,
        page: PageInput = 1,
        limit: SearchLimitInput = 10,
    ) -> dict[str, Any]:
        """Find KudaGo city news for a supported city.

        The city must map to a KudaGo location. This tool does not support coordinate-radius searches, and the compact result is editorial news rather than an event schedule.
        """
        tool_name = "find_city_news"
        try:
            agent_request = FindCityNewsInput(
                city=city,
                location_slug=location_slug,
                only_current=only_current,
                page=page,
                limit=limit,
            )
            request = NewsSearchRequest(
                **city_payload(
                    city=agent_request.city,
                    location_slug=agent_request.location_slug,
                ),
                actual_only=agent_request.only_current,
                page=agent_request.page,
                page_size=agent_request.limit,
                lang="ru",
            )
        except ValidationError as exc:
            return validation_error(tool_name, exc)

        return await run_mcp_command(
            tool_name=tool_name,
            endpoint="mcp://tools/find_city_news",
            command="news.search",
            payload=request.model_dump(),
            request_text=agent_request.city or agent_request.location_slug.value,
            data_factory=serialize_news,
        )

    @mcp.tool(
        name="find_city_guides",
        annotations=READ_ONLY_TOOL_ANNOTATIONS,
        version=MCP_FACADE_VERSION,
    )
    async def find_city_guides(
        city: CityInput = None,
        location_slug: LocationSlugInput = None,
        page: PageInput = 1,
        limit: SearchLimitInput = 10,
    ) -> dict[str, Any]:
        """Find editorial KudaGo city guides and curated lists.

        A guide may reference events, places or movies. It is editorial content, not a live schedule or route, and requires a city that maps to KudaGo.
        """
        tool_name = "find_city_guides"
        try:
            agent_request = FindCityGuidesInput(
                city=city,
                location_slug=location_slug,
                page=page,
                limit=limit,
            )
            request = ListsSearchRequest(
                **city_payload(
                    city=agent_request.city,
                    location_slug=agent_request.location_slug,
                ),
                page=agent_request.page,
                page_size=agent_request.limit,
                lang="ru",
            )
        except ValidationError as exc:
            return validation_error(tool_name, exc)

        return await run_mcp_command(
            tool_name=tool_name,
            endpoint="mcp://tools/find_city_guides",
            command="lists.search",
            payload=request.model_dump(),
            request_text=agent_request.city or agent_request.location_slug.value,
            data_factory=serialize_guides,
        )


__all__ = ["register_content_tools"]

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from urllib.parse import quote

from .http_client import JsonData, KudaGoHttpClient

TimeParam = int | str | datetime
DateParam = str | date
FieldParam = str | list[str] | tuple[str, ...]
IdListParam = int | list[int] | tuple[int, ...]
SlugListParam = str | list[str] | tuple[str, ...]


def _segment(value: int | str) -> str:
    return quote(str(value), safe="")


async def event_categories(client: KudaGoHttpClient, *, lang: str | None = None, order_by: FieldParam | None = None, fields: FieldParam | None = None) -> JsonData:
    """GET /public-api/v1.4/event-categories/"""
    return await client.get("event-categories/", {"lang": lang, "order_by": order_by, "fields": fields})


async def place_categories(client: KudaGoHttpClient, *, lang: str | None = None, order_by: FieldParam | None = None, fields: FieldParam | None = None) -> JsonData:
    """GET /public-api/v1.4/place-categories/"""
    return await client.get("place-categories/", {"lang": lang, "order_by": order_by, "fields": fields})


async def locations(client: KudaGoHttpClient, *, lang: str | None = None, fields: FieldParam | None = None, order_by: FieldParam | None = None) -> JsonData:
    """GET /public-api/v1.4/locations/"""
    return await client.get("locations/", {"lang": lang, "fields": fields, "order_by": order_by})


async def location(client: KudaGoHttpClient, slug: str, *, lang: str | None = None, fields: FieldParam | None = None) -> JsonData:
    """GET /public-api/v1.4/locations/{slug}/"""
    return await client.get(f"locations/{_segment(slug)}/", {"lang": lang, "fields": fields})


async def search(
    client: KudaGoHttpClient,
    q: str,
    *,
    lang: str | None = None,
    page: int | None = None,
    page_size: int | None = None,
    expand: FieldParam | None = None,
    location: str | None = None,
    ctype: str | None = None,
    is_free: bool | int | str | None = None,
    include_inactual: bool | int | str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    radius: int | None = None,
) -> JsonData:
    """GET /public-api/v1.4/search/"""
    return await client.get("search/", {"q": q, "lang": lang, "page": page, "page_size": page_size, "expand": expand, "location": location, "ctype": ctype, "is_free": is_free, "include_inactual": include_inactual, "lat": lat, "lon": lon, "radius": radius})


async def events(
    client: KudaGoHttpClient,
    *,
    lang: str | None = None,
    page: int | None = None,
    page_size: int | None = None,
    fields: FieldParam | None = None,
    expand: FieldParam | None = None,
    order_by: FieldParam | None = None,
    text_format: str | None = None,
    ids: IdListParam | None = None,
    location: str | None = None,
    actual_since: TimeParam | None = None,
    actual_until: TimeParam | None = None,
    place_id: int | None = None,
    parent_id: int | None = None,
    is_free: bool | int | str | None = None,
    categories: SlugListParam | None = None,
    tags: SlugListParam | None = None,
    lon: float | None = None,
    lat: float | None = None,
    radius: int | None = None,
) -> JsonData:
    """GET /public-api/v1.4/events/"""
    return await client.get("events/", {"lang": lang, "page": page, "page_size": page_size, "fields": fields, "expand": expand, "order_by": order_by, "text_format": text_format, "ids": ids, "location": location, "actual_since": actual_since, "actual_until": actual_until, "place_id": place_id, "parent_id": parent_id, "is_free": is_free, "categories": categories, "tags": tags, "lon": lon, "lat": lat, "radius": radius})


async def event(client: KudaGoHttpClient, event_id: int, *, lang: str | None = None, fields: FieldParam | None = None, expand: FieldParam | None = None) -> JsonData:
    """GET /public-api/v1.4/events/{event_id}/"""
    return await client.get(f"events/{_segment(event_id)}/", {"lang": lang, "fields": fields, "expand": expand})


async def event_comments(client: KudaGoHttpClient, event_id: int, *, lang: str | None = None, page: int | None = None, page_size: int | None = None, fields: FieldParam | None = None, order_by: FieldParam | None = None, ids: IdListParam | None = None) -> JsonData:
    """GET /public-api/v1.4/events/{event_id}/comments/"""
    return await client.get(f"events/{_segment(event_id)}/comments/", {"lang": lang, "page": page, "page_size": page_size, "fields": fields, "order_by": order_by, "ids": ids})


async def events_of_the_day(client: KudaGoHttpClient, *, lang: str | None = None, page: int | None = None, page_size: int | None = None, fields: FieldParam | None = None, expand: FieldParam | None = None, order_by: FieldParam | None = None, text_format: str | None = None, location: str | None = None, date: DateParam | None = None) -> JsonData:
    """GET /public-api/v1.4/events-of-the-day/"""
    return await client.get("events-of-the-day/", {"lang": lang, "page": page, "page_size": page_size, "fields": fields, "expand": expand, "order_by": order_by, "text_format": text_format, "location": location, "date": date})


async def news(client: KudaGoHttpClient, *, lang: str | None = None, page: int | None = None, page_size: int | None = None, fields: FieldParam | None = None, expand: FieldParam | None = None, order_by: FieldParam | None = None, text_format: str | None = None, ids: IdListParam | None = None, tags: SlugListParam | None = None, location: str | None = None, actual_only: bool | int | str | None = None) -> JsonData:
    """GET /public-api/v1.4/news/"""
    return await client.get("news/", {"lang": lang, "page": page, "page_size": page_size, "fields": fields, "expand": expand, "order_by": order_by, "text_format": text_format, "ids": ids, "tags": tags, "location": location, "actual_only": actual_only})


async def news_detail(client: KudaGoHttpClient, news_id: int, *, lang: str | None = None, fields: FieldParam | None = None, expand: FieldParam | None = None) -> JsonData:
    """GET /public-api/v1.4/news/{news_id}/"""
    return await client.get(f"news/{_segment(news_id)}/", {"lang": lang, "fields": fields, "expand": expand})


async def news_comments(client: KudaGoHttpClient, news_id: int, *, lang: str | None = None, page: int | None = None, page_size: int | None = None, fields: FieldParam | None = None, order_by: FieldParam | None = None, ids: IdListParam | None = None) -> JsonData:
    """GET /public-api/v1.4/news/{news_id}/comments/"""
    return await client.get(f"news/{_segment(news_id)}/comments/", {"lang": lang, "page": page, "page_size": page_size, "fields": fields, "order_by": order_by, "ids": ids})


async def lists(client: KudaGoHttpClient, *, lang: str | None = None, page: int | None = None, page_size: int | None = None, fields: FieldParam | None = None, expand: FieldParam | None = None, order_by: FieldParam | None = None, text_format: str | None = None, ids: IdListParam | None = None, tags: SlugListParam | None = None, location: str | None = None) -> JsonData:
    """GET /public-api/v1.4/lists/"""
    return await client.get("lists/", {"lang": lang, "page": page, "page_size": page_size, "fields": fields, "expand": expand, "order_by": order_by, "text_format": text_format, "ids": ids, "tags": tags, "location": location})


async def list_detail(client: KudaGoHttpClient, list_id: int, *, lang: str | None = None, fields: FieldParam | None = None, expand: FieldParam | None = None) -> JsonData:
    """GET /public-api/v1.4/lists/{list_id}/"""
    return await client.get(f"lists/{_segment(list_id)}/", {"lang": lang, "fields": fields, "expand": expand})


async def list_comments(client: KudaGoHttpClient, list_id: int, *, lang: str | None = None, page: int | None = None, page_size: int | None = None, fields: FieldParam | None = None, order_by: FieldParam | None = None, ids: IdListParam | None = None) -> JsonData:
    """GET /public-api/v1.4/lists/{list_id}/comments/"""
    return await client.get(f"lists/{_segment(list_id)}/comments/", {"lang": lang, "page": page, "page_size": page_size, "fields": fields, "order_by": order_by, "ids": ids})


async def places(client: KudaGoHttpClient, *, lang: str | None = None, page: int | None = None, page_size: int | None = None, fields: FieldParam | None = None, expand: FieldParam | None = None, order_by: FieldParam | None = None, text_format: str | None = None, ids: IdListParam | None = None, location: str | None = None, has_showings: str | None = None, showing_since: TimeParam | None = None, showing_until: TimeParam | None = None, is_free: bool | int | str | None = None, categories: SlugListParam | None = None, tags: SlugListParam | None = None, parent_id: int | None = None, lon: float | None = None, lat: float | None = None, radius: int | None = None) -> JsonData:
    """GET /public-api/v1.4/places/"""
    return await client.get("places/", {"lang": lang, "page": page, "page_size": page_size, "fields": fields, "expand": expand, "order_by": order_by, "text_format": text_format, "ids": ids, "location": location, "has_showings": has_showings, "showing_since": showing_since, "showing_until": showing_until, "is_free": is_free, "categories": categories, "tags": tags, "parent_id": parent_id, "lon": lon, "lat": lat, "radius": radius})


async def place_detail(client: KudaGoHttpClient, place_id: int, *, lang: str | None = None, fields: FieldParam | None = None, expand: FieldParam | None = None) -> JsonData:
    """GET /public-api/v1.4/places/{place_id}/"""
    return await client.get(f"places/{_segment(place_id)}/", {"lang": lang, "fields": fields, "expand": expand})


async def place_comments(client: KudaGoHttpClient, place_id: int, *, lang: str | None = None, page: int | None = None, page_size: int | None = None, fields: FieldParam | None = None, order_by: FieldParam | None = None, ids: IdListParam | None = None) -> JsonData:
    """GET /public-api/v1.4/places/{place_id}/comments/"""
    return await client.get(f"places/{_segment(place_id)}/comments/", {"lang": lang, "page": page, "page_size": page_size, "fields": fields, "order_by": order_by, "ids": ids})


async def movies(client: KudaGoHttpClient, *, lang: str | None = None, page: int | None = None, page_size: int | None = None, fields: FieldParam | None = None, expand: FieldParam | None = None, order_by: FieldParam | None = None, text_format: str | None = None, ids: IdListParam | None = None, tags: SlugListParam | None = None, location: str | None = None, premiering_in_location: str | None = None, is_free: bool | int | str | None = None, place: int | None = None, actual_since: TimeParam | None = None, actual_until: TimeParam | None = None) -> JsonData:
    """GET /public-api/v1.4/movies/"""
    return await client.get("movies/", {"lang": lang, "page": page, "page_size": page_size, "fields": fields, "expand": expand, "order_by": order_by, "text_format": text_format, "ids": ids, "tags": tags, "location": location, "premiering_in_location": premiering_in_location, "is_free": is_free, "place": place, "actual_since": actual_since, "actual_until": actual_until})


async def movie_detail(client: KudaGoHttpClient, movie_id: int, *, lang: str | None = None, fields: FieldParam | None = None, expand: FieldParam | None = None) -> JsonData:
    """GET /public-api/v1.4/movies/{movie_id}/"""
    return await client.get(f"movies/{_segment(movie_id)}/", {"lang": lang, "fields": fields, "expand": expand})


async def movie_showings_for_movie(client: KudaGoHttpClient, movie_id: int, *, lang: str | None = None, page: int | None = None, page_size: int | None = None, fields: FieldParam | None = None, expand: FieldParam | None = None, order_by: FieldParam | None = None, location: str | None = None, actual_since: TimeParam | None = None, actual_until: TimeParam | None = None, place: int | None = None, is_free: bool | int | str | None = None) -> JsonData:
    """GET /public-api/v1.4/movies/{movie_id}/showings/"""
    return await client.get(f"movies/{_segment(movie_id)}/showings/", {"lang": lang, "page": page, "page_size": page_size, "fields": fields, "expand": expand, "order_by": order_by, "location": location, "actual_since": actual_since, "actual_until": actual_until, "place": place, "is_free": is_free})


async def movie_comments(client: KudaGoHttpClient, movie_id: int, *, lang: str | None = None, page: int | None = None, page_size: int | None = None, fields: FieldParam | None = None, order_by: FieldParam | None = None, ids: IdListParam | None = None) -> JsonData:
    """GET /public-api/v1.4/movies/{movie_id}/comments/"""
    return await client.get(f"movies/{_segment(movie_id)}/comments/", {"lang": lang, "page": page, "page_size": page_size, "fields": fields, "order_by": order_by, "ids": ids})


async def movie_showings(client: KudaGoHttpClient, *, lang: str | None = None, page: int | None = None, page_size: int | None = None, fields: FieldParam | None = None, expand: FieldParam | None = None, ids: IdListParam | None = None, location: str | None = None, actual_since: TimeParam | None = None, actual_until: TimeParam | None = None, place_id: int | None = None, order_by: FieldParam | None = None, is_free: bool | int | str | None = None) -> JsonData:
    """GET /public-api/v1.4/movie-showings/"""
    return await client.get("movie-showings/", {"lang": lang, "page": page, "page_size": page_size, "fields": fields, "expand": expand, "ids": ids, "location": location, "actual_since": actual_since, "actual_until": actual_until, "place_id": place_id, "order_by": order_by, "is_free": is_free})


async def movie_showing_detail(client: KudaGoHttpClient, showing_id: int, *, lang: str | None = None, fields: FieldParam | None = None, expand: FieldParam | None = None) -> JsonData:
    """GET /public-api/v1.4/movie-showings/{showing_id}/"""
    return await client.get(f"movie-showings/{_segment(showing_id)}/", {"lang": lang, "fields": fields, "expand": expand})


async def agents(client: KudaGoHttpClient, *, lang: str | None = None, page: int | None = None, page_size: int | None = None, text_format: str | None = None, ids: IdListParam | None = None, fields: FieldParam | None = None, expand: FieldParam | None = None, agent_type: str | None = None, tags: SlugListParam | None = None) -> JsonData:
    """GET /public-api/v1.4/agents/"""
    return await client.get("agents/", {"lang": lang, "page": page, "page_size": page_size, "text_format": text_format, "ids": ids, "fields": fields, "expand": expand, "agent_type": agent_type, "tags": tags})


async def agent_detail(client: KudaGoHttpClient, agent_id: int, *, lang: str | None = None, text_format: str | None = None, fields: FieldParam | None = None) -> JsonData:
    """GET /public-api/v1.4/agents/{agent_id}/"""
    return await client.get(f"agents/{_segment(agent_id)}/", {"lang": lang, "text_format": text_format, "fields": fields})


async def agent_roles(client: KudaGoHttpClient, *, lang: str | None = None, page: int | None = None, page_size: int | None = None, fields: FieldParam | None = None) -> JsonData:
    """GET /public-api/v1.4/agent-roles/"""
    return await client.get("agent-roles/", {"lang": lang, "page": page, "page_size": page_size, "fields": fields})


async def agent_role_detail(client: KudaGoHttpClient, role_id: int, *, lang: str | None = None, fields: FieldParam | None = None) -> JsonData:
    """GET /public-api/v1.4/agent-roles/{role_id}/"""
    return await client.get(f"agent-roles/{_segment(role_id)}/", {"lang": lang, "fields": fields})


__all__ = [name for name, value in globals().items() if not name.startswith("_") and callable(value) and name not in {"Any", "quote"}]

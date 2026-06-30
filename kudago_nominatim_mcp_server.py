from __future__ import annotations

import argparse
import asyncio
import inspect
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from typing import Any

from mcp.server.fastmcp import FastMCP

import kudago_mcp_client as kudago
from kudago_mcp_client import KudaGoHttpClient
from nominatim_geo_client import NominatimHttpClient
from nominatim_geo_client import search_settlement as nominatim_search_settlement

from kudago_nominatim_config import Settings, bool_env, load_settings
from kudago_nominatim_geo import resolve_geo_for_kudago
from kudago_nominatim_utils import clean_optional_text, clamp_int, csv_or_none, status_error, status_ok

settings: Settings = load_settings()
logger = logging.getLogger("KudaGoNominatimMCP")
mcp = FastMCP(name="kudago-nominatim")

kudago_client = KudaGoHttpClient(
    base_url=settings.kudago_base_url,
    user_agent="kudago-nominatim-mcp/0.1.0",
    trust_env=settings.trust_env,
)
nominatim_client = NominatimHttpClient(
    base_url=settings.nominatim_base_url,
    user_agent=settings.nominatim_user_agent,
    referer=settings.nominatim_referer,
    min_interval_seconds=settings.nominatim_min_interval_seconds,
    trust_env=settings.trust_env,
)


def _lang(lang: str | None) -> str:
    return clean_optional_text(lang) or settings.default_lang


def _page_size(value: int, default: int = 10) -> int:
    return clamp_int(value, 1, 100, default)


def _page(value: int, default: int = 1) -> int:
    return clamp_int(value, 1, 10_000, default)


async def _resolve_geo(
    *,
    tool: str,
    location: str | None = None,
    place_query: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    radius: int | None = None,
    allow_coordinates: bool = True,
    lang: str | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    resolved = await resolve_geo_for_kudago(
        kudago_client=kudago_client,
        nominatim_client=nominatim_client,
        location=clean_optional_text(location),
        place_query=clean_optional_text(place_query),
        lat=lat,
        lon=lon,
        radius=radius,
        allow_coordinates=allow_coordinates,
        lang=_lang(lang),
        countrycodes=settings.default_countrycodes,
        default_radius=settings.default_radius,
        email=settings.nominatim_email,
    )
    geo = resolved.as_dict()
    if resolved.status != "ok":
        return status_error(tool, resolved.message or resolved.status, geo=geo), geo
    return None, geo


def _location_from_geo(geo: dict[str, Any]) -> str | None:
    return geo.get("location") if geo.get("kind") == "kudago_location" else None


def _lat_from_geo(geo: dict[str, Any]) -> float | None:
    return geo.get("lat") if geo.get("kind") == "coordinates" else None


def _lon_from_geo(geo: dict[str, Any]) -> float | None:
    return geo.get("lon") if geo.get("kind") == "coordinates" else None


def _radius_from_geo(geo: dict[str, Any]) -> int | None:
    return geo.get("radius") if geo.get("kind") == "coordinates" else None


async def _with_errors(tool: str, coro: Any, **extra: Any) -> dict[str, Any]:
    try:
        data = await coro
        return status_ok(tool, data, **extra)
    except Exception as exc:
        logger.exception("Tool %s failed", tool)
        return status_error(tool, str(exc), error_type=exc.__class__.__name__, **extra)


# ---------------------------------------------------------------------------
# TOOLS / BUSINESS LOGIC
# ---------------------------------------------------------------------------


@mcp.tool()
async def resolve_place(query: str, countrycodes: str | None = None, limit: int = 5, accept_language: str | None = None) -> dict[str, Any]:
    """Геокодирует название места через Nominatim и возвращает raw candidates с lat/lon.

    Используй, когда пользователь указал место обычным текстом, а для дальнейшего поиска нужны координаты
    или нужно проверить неоднозначность: город, район, адрес, достопримечательность, "рядом с ...".
    Этот инструмент ничего не выбирает за агента и не вызывает KudaGo: он только возвращает кандидатов.

    Параметры: query — название места; countrycodes — ISO-коды стран через запятую, например ru или ru,de;
    limit=1..10; accept_language=ru|en. Если кандидатов несколько, уточни место у пользователя или передай
    выбранные lat, lon, radius в events/search/places.
    """
    query = clean_optional_text(query)
    if not query:
        return status_error("resolve_place", "query must not be empty")
    try:
        data = await nominatim_search_settlement(
            nominatim_client,
            q=query,
            countrycodes=clean_optional_text(countrycodes) or settings.default_countrycodes,
            limit=clamp_int(limit, 1, 10, 5),
            accept_language=clean_optional_text(accept_language) or settings.default_lang,
            addressdetails=True,
            extratags=True,
            namedetails=True,
            email=settings.nominatim_email,
        )
        return status_ok("resolve_place", data, query=query)
    except Exception as exc:
        logger.exception("Tool resolve_place failed")
        return status_error("resolve_place", str(exc), error_type=exc.__class__.__name__, query=query)


@mcp.tool()
async def reference(kind: str, slug: str | None = None, role_id: int | None = None, lang: str | None = None) -> dict[str, Any]:
    """Справочники KudaGo: event_categories, place_categories, locations, location, agent_roles, agent_role.

    Используй перед фильтрацией, если агенту нужен slug категории события/места, slug города KudaGo или роль
    агента. kind принимает строго: event_categories|place_categories|locations|location|agent_roles|agent_role.
    Для kind=location передай slug, например msk или spb. Для kind=agent_role передай role_id.
    Возвращает raw JSON KudaGo без нормализации.
    """
    kind = (kind or "").strip().lower()
    lang_value = _lang(lang)
    if kind == "event_categories":
        return await _with_errors("reference", kudago.event_categories(kudago_client, lang=lang_value), kind=kind)
    if kind == "place_categories":
        return await _with_errors("reference", kudago.place_categories(kudago_client, lang=lang_value), kind=kind)
    if kind == "locations":
        return await _with_errors("reference", kudago.locations(kudago_client, lang=lang_value), kind=kind)
    if kind == "location":
        if not slug:
            return status_error("reference", "slug is required for kind=location", kind=kind)
        return await _with_errors("reference", kudago.location(kudago_client, slug, lang=lang_value), kind=kind)
    if kind == "agent_roles":
        return await _with_errors("reference", kudago.agent_roles(kudago_client, lang=lang_value), kind=kind)
    if kind == "agent_role":
        if role_id is None:
            return status_error("reference", "role_id is required for kind=agent_role", kind=kind)
        return await _with_errors("reference", kudago.agent_role_detail(kudago_client, role_id, lang=lang_value), kind=kind)
    return status_error("reference", "Unknown reference kind", kind=kind)


@mcp.tool()
async def search(
    query: str,
    ctype: str = "event",
    location: str | None = None,
    place_query: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    radius: int | None = None,
    is_free: bool | None = None,
    include_inactual: bool = False,
    expand: str | None = None,
    page: int = 1,
    page_size: int = 10,
    lang: str | None = None,
) -> dict[str, Any]:
    """Полнотекстовый поиск KudaGo по query: ctype=event|place|news|list.

    Используй, когда есть текстовый запрос пользователя: "джаз", "выставка", "музей", "куда сходить".
    Для мероприятий обычно ctype=event, для мест ctype=place. Для строгой фильтрации по датам и категориям
    лучше используй events, а не search. location — slug города KudaGo, например msk/spb. Если пользователь
    дал обычное название города, передай place_query: сервер сначала попробует найти точный KudaGo location,
    затем при необходимости вернёт Nominatim-кандидатов или координаты.
    """
    query = clean_optional_text(query)
    if not query:
        return status_error("search", "query must not be empty")
    early, geo = await _resolve_geo(tool="search", location=location, place_query=place_query, lat=lat, lon=lon, radius=radius, allow_coordinates=True, lang=lang)
    if early:
        return early
    return await _with_errors(
        "search",
        kudago.search(kudago_client, q=query, lang=_lang(lang), page=_page(page), page_size=_page_size(page_size), expand=expand, location=_location_from_geo(geo), ctype=ctype, is_free=is_free, include_inactual=include_inactual, lat=_lat_from_geo(geo), lon=_lon_from_geo(geo), radius=_radius_from_geo(geo)),
        query=query,
        ctype=ctype,
        geo=geo,
    )


@mcp.tool()
async def events(
    location: str | None = None,
    place_query: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    radius: int | None = None,
    actual_since: str | int | None = None,
    actual_until: str | int | None = None,
    categories: str | None = None,
    tags: str | None = None,
    is_free: bool | None = None,
    fields: str | None = "id,title,short_title,dates,place,location,categories,tags,price,is_free,site_url,age_restriction",
    expand: str | None = "dates,place,location",
    order_by: str = "-publication_date",
    page: int = 1,
    page_size: int = 10,
    lang: str | None = None,
) -> dict[str, Any]:
    """Список событий KudaGo через /events/ с детерминированными фильтрами.

    Используй для запросов с датами, категориями, бесплатностью, городом, координатами или радиусом:
    "концерты завтра в Москве", "бесплатные выставки на выходных", "события рядом". Это не текстовый
    поиск по словам; если нужен поиск по фразе, используй search с ctype=event. categories и tags — slug-и
    через запятую; исключение можно задавать минусом: concert,-kids. actual_since/actual_until передавай
    как Unix timestamp или ISO 8601. location — slug KudaGo; place_query — обычное название места.
    """
    early, geo = await _resolve_geo(tool="events", location=location, place_query=place_query, lat=lat, lon=lon, radius=radius, allow_coordinates=True, lang=lang)
    if early:
        return early
    return await _with_errors(
        "events",
        kudago.events(kudago_client, lang=_lang(lang), page=_page(page), page_size=_page_size(page_size), fields=csv_or_none(fields), expand=csv_or_none(expand), order_by=order_by, text_format="text", location=_location_from_geo(geo), actual_since=actual_since, actual_until=actual_until, is_free=is_free, categories=csv_or_none(categories), tags=csv_or_none(tags), lon=_lon_from_geo(geo), lat=_lat_from_geo(geo), radius=_radius_from_geo(geo)),
        geo=geo,
    )


@mcp.tool()
async def events_of_the_day(location: str | None = None, place_query: str | None = None, date: str | None = None, page_size: int = 10, lang: str | None = None) -> dict[str, Any]:
    """События дня, выбранные редакцией KudaGo.

    Используй, когда пользователь просит "лучшие события сегодня", "куда сходить сегодня", "афиша дня",
    "рекомендации редакции". Этот endpoint требует KudaGo location slug и не поддерживает Nominatim-координаты.
    Если пользователь дал обычное название города, передай place_query: сервер попробует найти точное совпадение
    среди KudaGo locations. date — YYYY-MM-DD, если нужна конкретная дата.
    """
    early, geo = await _resolve_geo(tool="events_of_the_day", location=location, place_query=place_query, allow_coordinates=False, lang=lang)
    if early:
        return early
    return await _with_errors("events_of_the_day", kudago.events_of_the_day(kudago_client, lang=_lang(lang), page_size=_page_size(page_size), fields="id,title,dates,place,location,categories,site_url", expand="dates,place,location", text_format="text", location=_location_from_geo(geo), date=date), geo=geo)


@mcp.tool()
async def places(
    location: str | None = None,
    place_query: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    radius: int | None = None,
    categories: str | None = None,
    tags: str | None = None,
    has_showings: str | None = None,
    fields: str | None = "id,title,slug,address,phone,site_url,subway,coords,location,categories,tags,images",
    expand: str | None = "location,categories",
    page: int = 1,
    page_size: int = 10,
    lang: str | None = None,
) -> dict[str, Any]:
    """Список мест KudaGo через /places/.

    Используй для заведений, музеев, театров, кинотеатров, парков и других мест без обязательного текстового
    запроса. Для текстового поиска по местам лучше search с ctype=place. location — slug KudaGo; place_query —
    обычное название города/района, которое можно разрешить через KudaGo locations или Nominatim. categories и
    tags — slug-и через запятую. Для кинотеатров с сеансами можно использовать has_showings=true.
    """
    early, geo = await _resolve_geo(tool="places", location=location, place_query=place_query, lat=lat, lon=lon, radius=radius, allow_coordinates=True, lang=lang)
    if early:
        return early
    return await _with_errors("places", kudago.places(kudago_client, lang=_lang(lang), page=_page(page), page_size=_page_size(page_size), fields=csv_or_none(fields), expand=csv_or_none(expand), text_format="text", location=_location_from_geo(geo), has_showings=has_showings, categories=csv_or_none(categories), tags=csv_or_none(tags), lon=_lon_from_geo(geo), lat=_lat_from_geo(geo), radius=_radius_from_geo(geo)), geo=geo)


@mcp.tool()
async def news(location: str | None = None, place_query: str | None = None, tags: str | None = None, actual_only: bool | None = None, page: int = 1, page_size: int = 10, lang: str | None = None) -> dict[str, Any]:
    """Список новостей KudaGo.

    Используй, когда пользователь спрашивает новости, публикации, городские обновления или свежие материалы
    KudaGo. Для текстового поиска по новостям используй search с ctype=news. Этот endpoint работает по KudaGo
    location slug; координаты Nominatim здесь не используются. tags — slug-и через запятую.
    """
    early, geo = await _resolve_geo(tool="news", location=location, place_query=place_query, allow_coordinates=False, lang=lang)
    if early:
        return early
    return await _with_errors("news", kudago.news(kudago_client, lang=_lang(lang), page=_page(page), page_size=_page_size(page_size), fields="id,title,publication_date,slug,site_url,description,location,tags", text_format="text", location=_location_from_geo(geo), tags=csv_or_none(tags), actual_only=actual_only, order_by="-publication_date"), geo=geo)


@mcp.tool()
async def lists(location: str | None = None, place_query: str | None = None, tags: str | None = None, page: int = 1, page_size: int = 10, lang: str | None = None) -> dict[str, Any]:
    """Список подборок KudaGo.

    Используй для запросов вроде "подборки мест", "лучшие рестораны", "куда сходить с детьми", "топ мест".
    Для текстового поиска по подборкам используй search с ctype=list. Этот endpoint работает по KudaGo location
    slug; координаты Nominatim здесь не используются. tags — slug-и через запятую.
    """
    early, geo = await _resolve_geo(tool="lists", location=location, place_query=place_query, allow_coordinates=False, lang=lang)
    if early:
        return early
    return await _with_errors("lists", kudago.lists(kudago_client, lang=_lang(lang), page=_page(page), page_size=_page_size(page_size), fields="id,title,slug,description,site_url,location,tags", text_format="text", location=_location_from_geo(geo), tags=csv_or_none(tags), order_by="-publication_date"), geo=geo)


@mcp.tool()
async def movies(location: str | None = None, place_query: str | None = None, actual_since: str | int | None = None, actual_until: str | int | None = None, premiering_in_location: str | None = None, place_id: int | None = None, page: int = 1, page_size: int = 10, lang: str | None = None) -> dict[str, Any]:
    """Список фильмов KudaGo.

    Используй, когда пользователь спрашивает фильмы в прокате, премьеры или киноафишу без конкретного сеанса.
    Для сеансов конкретного фильма сначала найди movie_id, затем используй movie_showings. Этот endpoint работает
    по KudaGo location slug; координаты Nominatim здесь не используются. place_id передаётся в KudaGo как query
    parameter place, потому что так он назван в URI-шаблоне API.
    """
    early, geo = await _resolve_geo(tool="movies", location=location, place_query=place_query, allow_coordinates=False, lang=lang)
    if early:
        return early
    return await _with_errors("movies", kudago.movies(kudago_client, lang=_lang(lang), page=_page(page), page_size=_page_size(page_size), fields="id,title,slug,description,site_url,poster,genres,running_time,age_restriction", text_format="text", location=_location_from_geo(geo), premiering_in_location=premiering_in_location, place=place_id, actual_since=actual_since, actual_until=actual_until), geo=geo)


@mcp.tool()
async def movie_showings(movie_id: int | None = None, showing_id: int | None = None, location: str | None = None, place_query: str | None = None, actual_since: str | int | None = None, actual_until: str | int | None = None, place_id: int | None = None, is_free: bool | None = None, page: int = 1, page_size: int = 10, lang: str | None = None) -> dict[str, Any]:
    """Киносеансы KudaGo: детализация показа, показы конкретного фильма или общий список показов.

    Если передан showing_id — вернёт /movie-showings/{showing_id}/. Если передан movie_id — вернёт
    /movies/{movie_id}/showings/. Если movie_id и showing_id не переданы — вернёт /movie-showings/.
    Используй для запросов "сеансы фильма", "где показывают", "кино сегодня", "расписание кино".
    Работает по KudaGo location slug; координаты Nominatim здесь не используются.
    """
    if showing_id is not None:
        return await _with_errors("movie_showings", kudago.movie_showing_detail(kudago_client, showing_id, lang=_lang(lang)), mode="showing_detail")
    early, geo = await _resolve_geo(tool="movie_showings", location=location, place_query=place_query, allow_coordinates=False, lang=lang)
    if early:
        return early
    if movie_id is not None:
        return await _with_errors("movie_showings", kudago.movie_showings_for_movie(kudago_client, movie_id, lang=_lang(lang), page=_page(page), page_size=_page_size(page_size), fields="id,movie,place,datetime,three_d,imax,four_dx,original_language,price", expand="movie,place", location=_location_from_geo(geo), actual_since=actual_since, actual_until=actual_until, place=place_id, is_free=is_free), mode="movie_showings_for_movie", geo=geo)
    return await _with_errors("movie_showings", kudago.movie_showings(kudago_client, lang=_lang(lang), page=_page(page), page_size=_page_size(page_size), fields="id,movie,place,datetime,three_d,imax,four_dx,original_language,price", expand="movie,place", location=_location_from_geo(geo), actual_since=actual_since, actual_until=actual_until, place_id=place_id, is_free=is_free), mode="movie_showings", geo=geo)


@mcp.tool()
async def agents(agent_id: int | None = None, agent_type: str | None = None, tags: str | None = None, page: int = 1, page_size: int = 10, lang: str | None = None) -> dict[str, Any]:
    """Агенты KudaGo: персоны и организации, связанные с событиями.

    Если agent_id не передан — вернёт список агентов. Если agent_id передан — вернёт детализацию агента.
    Используй, когда нужно получить информацию об участнике, организаторе, артисте, персоне или организации
    из KudaGo. agent_type и tags можно использовать как низкоуровневые фильтры API.
    """
    if agent_id is not None:
        return await _with_errors("agents", kudago.agent_detail(kudago_client, agent_id, lang=_lang(lang), text_format="text"), mode="agent_detail")
    return await _with_errors("agents", kudago.agents(kudago_client, lang=_lang(lang), page=_page(page), page_size=_page_size(page_size), text_format="text", agent_type=agent_type, tags=csv_or_none(tags)), mode="agents")


@mcp.tool()
async def object(object_type: str, object_id: int | str, include_comments: bool = False, include_showings: bool = False, lang: str | None = None) -> dict[str, Any]:
    """Детализация одного объекта KudaGo по id или slug.

    object_type=event|news|list|place|movie|movie_showing|agent|agent_role|location. Используй после search,
    events, places, movies, lists или news, когда нужен полный объект. include_comments работает для
    event|news|list|place|movie и добавляет комментарии. include_showings работает для movie и добавляет
    список сеансов фильма. Для object_type=location object_id должен быть slug, например msk.
    """
    kind = (object_type or "").strip().lower()
    lang_value = _lang(lang)
    result: dict[str, Any] = {"status": "ok", "tool": "object", "object_type": kind, "object_id": object_id}
    try:
        if kind == "event":
            detail = await kudago.event(kudago_client, int(object_id), lang=lang_value, expand="dates,place,location")
            result["data"] = detail
            if include_comments:
                result["comments"] = await kudago.event_comments(kudago_client, int(object_id), lang=lang_value)
            return result
        if kind == "news":
            detail = await kudago.news_detail(kudago_client, int(object_id), lang=lang_value)
            result["data"] = detail
            if include_comments:
                result["comments"] = await kudago.news_comments(kudago_client, int(object_id), lang=lang_value)
            return result
        if kind == "list":
            detail = await kudago.list_detail(kudago_client, int(object_id), lang=lang_value)
            result["data"] = detail
            if include_comments:
                result["comments"] = await kudago.list_comments(kudago_client, int(object_id), lang=lang_value)
            return result
        if kind == "place":
            detail = await kudago.place_detail(kudago_client, int(object_id), lang=lang_value)
            result["data"] = detail
            if include_comments:
                result["comments"] = await kudago.place_comments(kudago_client, int(object_id), lang=lang_value)
            return result
        if kind == "movie":
            detail = await kudago.movie_detail(kudago_client, int(object_id), lang=lang_value)
            result["data"] = detail
            if include_comments:
                result["comments"] = await kudago.movie_comments(kudago_client, int(object_id), lang=lang_value)
            if include_showings:
                result["showings"] = await kudago.movie_showings_for_movie(kudago_client, int(object_id), lang=lang_value)
            return result
        if kind == "movie_showing":
            result["data"] = await kudago.movie_showing_detail(kudago_client, int(object_id), lang=lang_value)
            return result
        if kind == "agent":
            result["data"] = await kudago.agent_detail(kudago_client, int(object_id), lang=lang_value)
            return result
        if kind == "agent_role":
            result["data"] = await kudago.agent_role_detail(kudago_client, int(object_id), lang=lang_value)
            return result
        if kind == "location":
            result["data"] = await kudago.location(kudago_client, str(object_id), lang=lang_value)
            return result
        return status_error("object", "Unknown object_type", object_type=kind, object_id=object_id)
    except Exception as exc:
        logger.exception("Tool object failed")
        return status_error("object", str(exc), error_type=exc.__class__.__name__, object_type=kind, object_id=object_id)


@mcp.tool()
async def comments(object_type: str, object_id: int, page: int = 1, page_size: int = 20, lang: str | None = None) -> dict[str, Any]:
    """Комментарии к объекту KudaGo.

    object_type=event|news|list|place|movie. Используй только когда пользователь явно просит отзывы,
    комментарии, обсуждение или реакцию пользователей. Не вызывай автоматически для каждого объекта:
    комментарии увеличивают объём ответа и не нужны для обычной афиши.
    """
    kind = (object_type or "").strip().lower()
    common = {"lang": _lang(lang), "page": _page(page), "page_size": _page_size(page_size, 20)}
    if kind == "event":
        return await _with_errors("comments", kudago.event_comments(kudago_client, object_id, **common), object_type=kind)
    if kind == "news":
        return await _with_errors("comments", kudago.news_comments(kudago_client, object_id, **common), object_type=kind)
    if kind == "list":
        return await _with_errors("comments", kudago.list_comments(kudago_client, object_id, **common), object_type=kind)
    if kind == "place":
        return await _with_errors("comments", kudago.place_comments(kudago_client, object_id, **common), object_type=kind)
    if kind == "movie":
        return await _with_errors("comments", kudago.movie_comments(kudago_client, object_id, **common), object_type=kind)
    return status_error("comments", "object_type must be event|news|list|place|movie", object_type=kind)


# ---------------------------------------------------------------------------
# TRANSPORT SELECTOR AT STARTUP
# ---------------------------------------------------------------------------


def setup_logging(debug: bool = False) -> None:
    os.makedirs(settings.log_dir, exist_ok=True)
    level = logging.DEBUG if debug else logging.INFO
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    logger.setLevel(level)
    logger.handlers.clear()

    file_handler = RotatingFileHandler(
        filename=os.path.join(settings.log_dir, "kudago_nominatim_mcp.log"),
        maxBytes=8 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()  # stderr, safe for stdio MCP protocol
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


def normalize_transport(value: str | None) -> str:
    value = (value or "stdio").strip().lower().replace("_", "-")
    aliases = {
        "stdio": "stdio",
        "http": "streamable-http",
        "streamable-http": "streamable-http",
        "streamable": "streamable-http",
    }
    if value not in aliases:
        raise ValueError("transport must be stdio|http|streamable-http")
    return aliases[value]


def normalize_path(path: str | None) -> str:
    path = (path or "/mcp/").strip() or "/mcp/"
    if not path.startswith("/"):
        path = "/" + path
    if not path.endswith("/"):
        path += "/"
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KudaGo + Nominatim MCP Server")
    parser.add_argument("--debug", action="store_true", help="Включить подробное логирование")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "streamable-http", "streamable_http"],
        default=settings.mcp_transport,
        help="MCP transport. Default: stdio. Use http/streamable-http for localhost web-service mode.",
    )
    parser.add_argument("--host", default=settings.mcp_host, help="HTTP host. Use 127.0.0.1 for local-only mode.")
    parser.add_argument("--port", type=int, default=settings.mcp_port, help="HTTP port for streamable-http mode.")
    parser.add_argument("--path", default=settings.mcp_path, help="HTTP MCP path, default /mcp/.")
    return parser.parse_args()


async def run_stdio() -> None:
    logger.info("Запуск MCP-сервера KudaGo + Nominatim через stdio")
    await mcp.run_stdio_async()


def configure_streamable_http_settings(host: str, port: int, path: str) -> str:
    """Configure HTTP settings on the official MCP SDK FastMCP instance.

    In `mcp.server.fastmcp.FastMCP`, host/port/path are not passed to
    `mcp.run(...)`. They live in `mcp.settings` / constructor settings.
    This keeps one FastMCP instance and changes only the selected transport.
    """

    path = normalize_path(path)
    settings_obj = getattr(mcp, "settings", None)
    if settings_obj is None:
        logger.warning("FastMCP instance has no settings object; HTTP host/port/path may use SDK defaults")
        return path

    assignments = {
        "host": host,
        "port": port,
        "streamable_http_path": path,
    }
    for attr, value in assignments.items():
        if hasattr(settings_obj, attr):
            try:
                setattr(settings_obj, attr, value)
            except Exception as exc:
                logger.warning("Не удалось установить FastMCP setting %s=%r: %s", attr, value, exc)
        else:
            logger.debug("FastMCP settings has no %s attribute; skipping", attr)

    return path


def run_streamable_http(host: str, port: int, path: str) -> None:
    """Run FastMCP in Streamable HTTP mode.

    Important for the official `mcp.server.fastmcp.FastMCP`: `run()` accepts
    the transport name only. Host/port/path must be configured on `mcp.settings`
    or at FastMCP initialization, not passed as kwargs to `run()`.
    """

    path = configure_streamable_http_settings(host=host, port=port, path=path)
    logger.info("Запуск MCP-сервера KudaGo + Nominatim через Streamable HTTP: http://%s:%s%s", host, port, path)

    last_error: TypeError | None = None
    for transport_name in ("streamable-http", "http"):
        try:
            result = mcp.run(transport=transport_name)
            if inspect.isawaitable(result):
                asyncio.run(result)
            return
        except TypeError as exc:
            last_error = exc
            continue

    raise RuntimeError(f"FastMCP HTTP transport could not be started. Last TypeError: {last_error}")


async def shutdown_clients() -> None:
    await nominatim_client.close()
    await kudago_client.aclose()


def main() -> None:
    args = parse_args()
    transport = normalize_transport(args.transport)
    setup_logging(debug=args.debug or bool_env("DEBUG", False))

    try:
        if transport == "stdio":
            asyncio.run(run_stdio())
        elif transport == "streamable-http":
            run_streamable_http(host=args.host, port=args.port, path=args.path)
        else:
            raise ValueError(f"Unknown transport: {transport}")
    except KeyboardInterrupt:
        logger.info("Сервер остановлен пользователем")
    except Exception as exc:
        logger.exception("Критическая ошибка MCP-сервера: %s", exc)
        sys.exit(1)
    finally:
        asyncio.run(shutdown_clients())
        logger.info("Работа MCP-сервера завершена")


def cli() -> None:
    main()


if __name__ == "__main__":
    cli()

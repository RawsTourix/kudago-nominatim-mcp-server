from __future__ import annotations

from typing import Any, Literal

from .http_client import JsonObject, NominatimHttpClient, NominatimParameterError, bool_int, comma_join

OutputFormat = Literal["xml", "json", "jsonv2", "geojson", "geocodejson"]
Layer = Literal["address", "poi", "railway", "natural", "manmade"]
FeatureType = Literal["country", "state", "city", "settlement"]


def _validate_limit(limit: int | None) -> int | None:
    if limit is None:
        return None
    if not 1 <= limit <= 40:
        raise NominatimParameterError("Nominatim search limit must be in range 1..40")
    return limit


def _polygon_flags(*, polygon_geojson: bool | int | None, polygon_kml: bool | int | None, polygon_svg: bool | int | None, polygon_text: bool | int | None) -> dict[str, int | None]:
    flags = {
        "polygon_geojson": bool_int(polygon_geojson),
        "polygon_kml": bool_int(polygon_kml),
        "polygon_svg": bool_int(polygon_svg),
        "polygon_text": bool_int(polygon_text),
    }
    enabled = [key for key, value in flags.items() if value == 1]
    if len(enabled) > 1:
        raise NominatimParameterError("Only one polygon output flag can be enabled at a time: " + ", ".join(enabled))
    return flags


def _common_search_params(
    *,
    format: OutputFormat | None,
    json_callback: str | None,
    limit: int | None,
    addressdetails: bool | int | None,
    extratags: bool | int | None,
    namedetails: bool | int | None,
    entrances: bool | int | None,
    accept_language: str | None,
    countrycodes: str | list[str] | None,
    layer: Layer | list[Layer] | None,
    featureType: FeatureType | None,
    exclude_place_ids: str | list[str | int] | None,
    viewbox: str | tuple[float, float, float, float] | None,
    bounded: bool | int | None,
    polygon_geojson: bool | int | None,
    polygon_kml: bool | int | None,
    polygon_svg: bool | int | None,
    polygon_text: bool | int | None,
    polygon_threshold: float | None,
    email: str | None,
    dedupe: bool | int | None,
    debug: bool | int | None,
) -> dict[str, Any]:
    if isinstance(viewbox, tuple):
        if len(viewbox) != 4:
            raise NominatimParameterError("viewbox tuple must contain exactly 4 numbers")
        viewbox_value: str | None = ",".join(str(value) for value in viewbox)
    else:
        viewbox_value = viewbox
    params: dict[str, Any] = {
        "format": format,
        "json_callback": json_callback,
        "limit": _validate_limit(limit),
        "addressdetails": bool_int(addressdetails),
        "extratags": bool_int(extratags),
        "namedetails": bool_int(namedetails),
        "entrances": bool_int(entrances),
        "accept-language": accept_language,
        "countrycodes": comma_join(countrycodes),
        "layer": comma_join(layer if isinstance(layer, list) else ([layer] if layer else None)),
        "featureType": featureType,
        "exclude_place_ids": comma_join(exclude_place_ids),
        "viewbox": viewbox_value,
        "bounded": bool_int(bounded),
        "polygon_threshold": polygon_threshold,
        "email": email,
        "dedupe": bool_int(dedupe),
        "debug": bool_int(debug),
    }
    params.update(_polygon_flags(polygon_geojson=polygon_geojson, polygon_kml=polygon_kml, polygon_svg=polygon_svg, polygon_text=polygon_text))
    return params


async def search(
    client: NominatimHttpClient,
    *,
    q: str,
    format: OutputFormat = "jsonv2",
    json_callback: str | None = None,
    limit: int | None = 10,
    addressdetails: bool | int | None = None,
    extratags: bool | int | None = None,
    namedetails: bool | int | None = None,
    entrances: bool | int | None = None,
    accept_language: str | None = None,
    countrycodes: str | list[str] | None = None,
    layer: Layer | list[Layer] | None = None,
    featureType: FeatureType | None = None,
    exclude_place_ids: str | list[str | int] | None = None,
    viewbox: str | tuple[float, float, float, float] | None = None,
    bounded: bool | int | None = None,
    polygon_geojson: bool | int | None = None,
    polygon_kml: bool | int | None = None,
    polygon_svg: bool | int | None = None,
    polygon_text: bool | int | None = None,
    polygon_threshold: float | None = None,
    email: str | None = None,
    dedupe: bool | int | None = None,
    debug: bool | int | None = None,
) -> list[JsonObject] | JsonObject:
    """GET /search with free-form q query."""
    if not q.strip():
        raise NominatimParameterError("q must be a non-empty string")
    params = _common_search_params(format=format, json_callback=json_callback, limit=limit, addressdetails=addressdetails, extratags=extratags, namedetails=namedetails, entrances=entrances, accept_language=accept_language, countrycodes=countrycodes, layer=layer, featureType=featureType, exclude_place_ids=exclude_place_ids, viewbox=viewbox, bounded=bounded, polygon_geojson=polygon_geojson, polygon_kml=polygon_kml, polygon_svg=polygon_svg, polygon_text=polygon_text, polygon_threshold=polygon_threshold, email=email, dedupe=dedupe, debug=debug)
    params["q"] = q
    data = await client.get("search", params)
    if isinstance(data, (list, dict)):
        return data
    raise NominatimParameterError("Expected Nominatim search response to be a list or object")


async def search_structured(
    client: NominatimHttpClient,
    *,
    amenity: str | None = None,
    street: str | None = None,
    city: str | None = None,
    county: str | None = None,
    state: str | None = None,
    country: str | None = None,
    postalcode: str | None = None,
    format: OutputFormat = "jsonv2",
    json_callback: str | None = None,
    limit: int | None = 10,
    addressdetails: bool | int | None = None,
    extratags: bool | int | None = None,
    namedetails: bool | int | None = None,
    entrances: bool | int | None = None,
    accept_language: str | None = None,
    countrycodes: str | list[str] | None = None,
    layer: Layer | list[Layer] | None = None,
    featureType: FeatureType | None = None,
    exclude_place_ids: str | list[str | int] | None = None,
    viewbox: str | tuple[float, float, float, float] | None = None,
    bounded: bool | int | None = None,
    polygon_geojson: bool | int | None = None,
    polygon_kml: bool | int | None = None,
    polygon_svg: bool | int | None = None,
    polygon_text: bool | int | None = None,
    polygon_threshold: float | None = None,
    email: str | None = None,
    dedupe: bool | int | None = None,
    debug: bool | int | None = None,
) -> list[JsonObject] | JsonObject:
    """GET /search with structured address parameters. No q argument by design."""
    structured = {"amenity": amenity, "street": street, "city": city, "county": county, "state": state, "country": country, "postalcode": postalcode}
    if not any(value and value.strip() for value in structured.values() if isinstance(value, str)):
        raise NominatimParameterError("At least one structured search field must be provided")
    params = _common_search_params(format=format, json_callback=json_callback, limit=limit, addressdetails=addressdetails, extratags=extratags, namedetails=namedetails, entrances=entrances, accept_language=accept_language, countrycodes=countrycodes, layer=layer, featureType=featureType, exclude_place_ids=exclude_place_ids, viewbox=viewbox, bounded=bounded, polygon_geojson=polygon_geojson, polygon_kml=polygon_kml, polygon_svg=polygon_svg, polygon_text=polygon_text, polygon_threshold=polygon_threshold, email=email, dedupe=dedupe, debug=debug)
    params.update(structured)
    data = await client.get("search", params)
    if isinstance(data, (list, dict)):
        return data
    raise NominatimParameterError("Expected Nominatim search response to be a list or object")


async def search_settlement(
    client: NominatimHttpClient,
    *,
    q: str,
    countrycodes: str | list[str] | None = None,
    accept_language: str | None = "ru",
    limit: int | None = 10,
    addressdetails: bool | int | None = True,
    extratags: bool | int | None = None,
    namedetails: bool | int | None = None,
    email: str | None = None,
    format: OutputFormat = "jsonv2",
) -> list[JsonObject] | JsonObject:
    """Convenience wrapper for named settlements: GET /search?featureType=settlement."""
    return await search(client, q=q, format=format, limit=limit, addressdetails=addressdetails, extratags=extratags, namedetails=namedetails, accept_language=accept_language, countrycodes=countrycodes, featureType="settlement", email=email)

from types import SimpleNamespace
from typing import Any

import pytest
from fastmcp import Client

from app.mcp.reference_data import REFERENCE_SNAPSHOT
from app.mcp.server import create_mcp_server


@pytest.mark.asyncio
async def test_actual_fastmcp_schemas_describe_every_public_property():
    server = create_mcp_server(
        settings_obj=SimpleNamespace(
            transitous_user_agent="tests/1.0 tests@example.com",
            openrouteservice_api_key="test-key",
        )
    )
    async with Client(server) as client:
        tools = await client.list_tools()

    for tool in tools:
        missing = _missing_property_descriptions(tool.inputSchema)
        assert missing == [], f"{tool.name} missing descriptions: {missing}"


@pytest.mark.asyncio
async def test_actual_fastmcp_schemas_expose_reference_enums_and_units():
    server = create_mcp_server(
        settings_obj=SimpleNamespace(
            transitous_user_agent="tests/1.0 tests@example.com",
            openrouteservice_api_key="test-key",
        )
    )
    async with Client(server) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}

    event_values = _enum_values(
        tools["find_events"].inputSchema["properties"]["categories"],
        tools["find_events"].inputSchema,
    )
    place_values = _enum_values(
        tools["find_places"].inputSchema["properties"]["categories"],
        tools["find_places"].inputSchema,
    )
    location_values = _enum_values(
        tools["find_events"].inputSchema["properties"]["location_slug"],
        tools["find_events"].inputSchema,
    )
    assert event_values == {
        item["slug"] for item in REFERENCE_SNAPSHOT["event_categories"]
    }
    assert place_values == {
        item["slug"] for item in REFERENCE_SNAPSHOT["place_categories"]
    }
    assert location_values == {
        item["slug"] for item in REFERENCE_SNAPSHOT["locations"]
    }
    assert "kilometres" in tools["find_events"].inputSchema["properties"][
        "radius_km"
    ]["description"]
    place_category_description = tools["find_places"].inputSchema["properties"][
        "categories"
    ]["description"]
    assert "theatre" in place_category_description
    assert "park" in place_category_description
    assert "theaters" not in place_category_description
    assert "parks" not in place_category_description
    showing_date_description = tools["find_movie_showings"].inputSchema[
        "properties"
    ]["date"]["description"]
    assert "next seven days" in showing_date_description
    assert "next seven days" in tools["find_movie_showings"].description


@pytest.mark.asyncio
async def test_actual_fastmcp_schemas_expose_defaults_limits_and_public_fields_only():
    server = create_mcp_server(
        settings_obj=SimpleNamespace(
            transitous_user_agent="tests/1.0 tests@example.com",
            openrouteservice_api_key="test-key",
        )
    )
    async with Client(server) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}

    events = tools["find_events"].inputSchema["properties"]
    assert events["page"]["default"] == 1
    assert events["limit"]["default"] == 10
    assert events["timezone"]["default"] is None
    assert _schema_value(events["page"], "minimum") == 1
    assert _schema_value(events["page"], "maximum") == 10_000
    assert _schema_value(events["limit"], "minimum") == 1
    assert _schema_value(events["limit"], "maximum") == 20
    assert _schema_value(events["radius_km"], "minimum") == 0.1
    assert _schema_value(events["radius_km"], "maximum") == 100
    assert {
        "actual_since",
        "actual_until",
        "include_past",
        "tags",
        "is_free",
        "page_size",
        "lang",
    }.isdisjoint(events)

    details = tools["get_details"].inputSchema
    assert set(details["required"]) == {"item_type", "item_id"}
    assert _enum_values(details["properties"]["item_type"], details) == {
        "event",
        "place",
        "movie",
        "movie_showing",
        "news",
        "guide",
    }

    transit = tools["plan_public_transport"].inputSchema["properties"]
    assert {"TRANSIT", "search_window_seconds", "arrive_by", "language"}.isdisjoint(
        transit
    )
    assert "TRANSIT" not in _enum_values(
        transit["modes"], tools["plan_public_transport"].inputSchema
    )
    street = tools["plan_street_route"].inputSchema["properties"]
    assert _enum_values(
        street["mode"], tools["plan_street_route"].inputSchema
    ) == {"walking", "cycling", "driving"}
    assert {"profile", "language", "include_geometry"}.isdisjoint(street)


def _missing_property_descriptions(
    schema: dict[str, Any],
    path: str = "",
) -> list[str]:
    missing: list[str] = []
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for name, subschema in properties.items():
            current = f"{path}.{name}" if path else name
            if not isinstance(subschema, dict) or not subschema.get("description"):
                missing.append(current)
            if isinstance(subschema, dict):
                missing.extend(_missing_property_descriptions(subschema, current))
    for key in ("items", "anyOf", "oneOf", "allOf"):
        nested = schema.get(key)
        if isinstance(nested, dict):
            missing.extend(_missing_property_descriptions(nested, path))
        elif isinstance(nested, list):
            for item in nested:
                if isinstance(item, dict):
                    missing.extend(_missing_property_descriptions(item, path))
    definitions = schema.get("$defs")
    if isinstance(definitions, dict):
        for name, definition in definitions.items():
            if isinstance(definition, dict):
                missing.extend(
                    _missing_property_descriptions(definition, f"$defs.{name}")
                )
    return missing


def _enum_values(
    schema: dict[str, Any],
    root: dict[str, Any] | None = None,
) -> set[str]:
    root = root or schema
    result = set(schema.get("enum", []))
    reference = schema.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/$defs/"):
        definition = root.get("$defs", {}).get(reference.removeprefix("#/$defs/"))
        if isinstance(definition, dict):
            result.update(_enum_values(definition, root))
    items = schema.get("items")
    if isinstance(items, dict):
        result.update(_enum_values(items, root))
    for key in ("anyOf", "oneOf", "allOf"):
        for item in schema.get(key, []):
            if isinstance(item, dict):
                result.update(_enum_values(item, root))
    return result


def _schema_value(schema: dict[str, Any], key: str) -> Any:
    if key in schema:
        return schema[key]
    if isinstance(schema.get("items"), dict):
        value = _schema_value(schema["items"], key)
        if value is not None:
            return value
    for branch_key in ("anyOf", "oneOf", "allOf"):
        for item in schema.get(branch_key, []):
            if isinstance(item, dict):
                value = _schema_value(item, key)
                if value is not None:
                    return value
    return None

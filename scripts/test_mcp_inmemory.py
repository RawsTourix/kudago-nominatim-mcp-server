import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from fastmcp import Client

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.mcp.server import create_mcp_server


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test MCP tools in memory")
    parser.add_argument("query", nargs="?", default="Нахабино")
    return parser.parse_args()


def print_result(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


async def run(query: str) -> None:
    async with Client(create_mcp_server()) as client:
        await client.ping()
        tools = await client.list_tools()
        tool_names = sorted(tool.name for tool in tools)
        print("TOOLS:", ", ".join(tool_names))
        assert {
            "events",
            "lists",
            "movie_showings",
            "movies",
            "news",
            "object",
            "places",
            "reference",
            "resolve_place",
        } <= set(tool_names)

        resolve_result = await client.call_tool(
            "resolve_place",
            {
                "query": query,
                "countrycodes": "ru",
                "limit": 5,
                "accept_language": "ru",
            },
            timeout=60.0,
        )

        events_result = await client.call_tool(
            "events",
            {"location": "msk", "page_size": 3, "lang": "ru"},
            timeout=60.0,
        )

        ambiguous_result = await client.call_tool(
            "events",
            {"place_query": "Нахабино", "page_size": 3, "lang": "ru"},
            timeout=60.0,
        )

        places_result = await client.call_tool(
            "places",
            {"location": "msk", "page_size": 3, "lang": "ru"},
            timeout=60.0,
        )

        places_ambiguous_result = await client.call_tool(
            "places",
            {"place_query": "Нахабино", "page_size": 3, "lang": "ru"},
            timeout=60.0,
        )

        news_result = await client.call_tool(
            "news",
            {"location": "msk", "page_size": 3, "lang": "ru"},
            timeout=60.0,
        )
        news_ambiguous_result = await client.call_tool(
            "news",
            {"place_query": "Нахабино", "page_size": 3, "lang": "ru"},
            timeout=60.0,
        )
        lists_result = await client.call_tool(
            "lists",
            {"location": "msk", "page_size": 3, "lang": "ru"},
            timeout=60.0,
        )
        lists_ambiguous_result = await client.call_tool(
            "lists",
            {"place_query": "Нахабино", "page_size": 3, "lang": "ru"},
            timeout=60.0,
        )
        movies_result = await client.call_tool(
            "movies",
            {"location": "msk", "page_size": 3, "lang": "ru"},
            timeout=60.0,
        )
        movies_ambiguous_result = await client.call_tool(
            "movies",
            {"place_query": "Нахабино", "page_size": 3, "lang": "ru"},
            timeout=60.0,
        )
        movie_showings_result = await client.call_tool(
            "movie_showings",
            {"location": "msk", "page_size": 3, "lang": "ru"},
            timeout=60.0,
        )
        movie_showings_ambiguous_result = await client.call_tool(
            "movie_showings",
            {"place_query": "Нахабино", "page_size": 3, "lang": "ru"},
            timeout=60.0,
        )
        reference_locations_result = await client.call_tool(
            "reference",
            {"kind": "locations", "lang": "ru"},
            timeout=60.0,
        )
        reference_categories_result = await client.call_tool(
            "reference",
            {"kind": "event_categories", "lang": "ru"},
            timeout=60.0,
        )
        reference_location_result = await client.call_tool(
            "reference",
            {"kind": "location", "slug": "msk", "lang": "ru"},
            timeout=60.0,
        )
        object_location_result = await client.call_tool(
            "object",
            {"object_type": "location", "object_id": "msk", "lang": "ru"},
            timeout=60.0,
        )
        event_object_result = None
        event_items = events_result.data["data"].get("items", [])
        if event_items:
            event_object_result = await client.call_tool(
                "object",
                {
                    "object_type": "event",
                    "object_id": str(event_items[0]["id"]),
                    "lang": "ru",
                },
                timeout=60.0,
            )

    print("RESOLVE_PLACE:")
    print_result(resolve_result.data)
    assert isinstance(resolve_result.data, dict)
    assert resolve_result.data["status"] == "ok"
    assert resolve_result.data["tool"] == "resolve_place"
    assert resolve_result.data["job_id"]

    print("EVENTS:")
    print_result(events_result.data)
    assert isinstance(events_result.data, dict)
    assert events_result.data["status"] == "ok"
    assert events_result.data["tool"] == "events"
    assert events_result.data["result_status"] == "ok"
    assert events_result.data["data"]["status"] == "ok"
    assert isinstance(events_result.data["data"]["items"], list)

    print("EVENTS AMBIGUOUS:")
    print_result(ambiguous_result.data)
    assert isinstance(ambiguous_result.data, dict)
    assert ambiguous_result.data["status"] == "ok"
    assert ambiguous_result.data["tool"] == "events"
    assert ambiguous_result.data["result_status"] == "geo_ambiguous"

    print("PLACES:")
    print_result(places_result.data)
    assert isinstance(places_result.data, dict)
    assert places_result.data["status"] == "ok"
    assert places_result.data["tool"] == "places"
    assert places_result.data["result_status"] == "ok"
    assert places_result.data["data"]["status"] == "ok"

    print("PLACES AMBIGUOUS:")
    print_result(places_ambiguous_result.data)
    assert isinstance(places_ambiguous_result.data, dict)
    assert places_ambiguous_result.data["status"] == "ok"
    assert places_ambiguous_result.data["tool"] == "places"
    assert places_ambiguous_result.data["result_status"] == "geo_ambiguous"

    for tool_name, result in (("news", news_result), ("lists", lists_result)):
        print(f"{tool_name.upper()}:")
        print_result(result.data)
        assert isinstance(result.data, dict)
        assert result.data["status"] == "ok"
        assert result.data["tool"] == tool_name
        assert result.data["result_status"] == "ok"
        assert result.data["data"]["status"] == "ok"

    for tool_name, result in (
        ("news", news_ambiguous_result),
        ("lists", lists_ambiguous_result),
    ):
        print(f"{tool_name.upper()} AMBIGUOUS:")
        print_result(result.data)
        assert isinstance(result.data, dict)
        assert result.data["status"] == "ok"
        assert result.data["tool"] == tool_name
        assert result.data["result_status"] == "geo_ambiguous"

    for result in (
        reference_locations_result,
        reference_categories_result,
        reference_location_result,
    ):
        print("REFERENCE:")
        print_result(result.data)
        assert isinstance(result.data, dict)
        assert result.data["status"] == "ok"
        assert result.data["tool"] == "reference"
        assert result.data["result_status"] == "ok"

    print("OBJECT LOCATION:")
    print_result(object_location_result.data)
    assert object_location_result.data["status"] == "ok"
    assert object_location_result.data["tool"] == "object"
    assert object_location_result.data["data"]["object_type"] == "location"

    if event_object_result is not None:
        print("OBJECT EVENT:")
        print_result(event_object_result.data)
        assert event_object_result.data["status"] == "ok"
        assert event_object_result.data["tool"] == "object"
        assert event_object_result.data["data"]["object_type"] == "event"

    for tool_name, result in (
        ("movies", movies_result),
        ("movie_showings", movie_showings_result),
    ):
        print(f"{tool_name.upper()}:")
        print_result(result.data)
        assert isinstance(result.data, dict)
        assert result.data["status"] == "ok"
        assert result.data["tool"] == tool_name
        assert result.data["result_status"] == "ok"
        assert result.data["data"]["status"] == "ok"

    for tool_name, result in (
        ("movies", movies_ambiguous_result),
        ("movie_showings", movie_showings_ambiguous_result),
    ):
        print(f"{tool_name.upper()} AMBIGUOUS:")
        print_result(result.data)
        assert isinstance(result.data, dict)
        assert result.data["status"] == "ok"
        assert result.data["tool"] == tool_name
        assert result.data["result_status"] == "geo_ambiguous"


if __name__ == "__main__":
    asyncio.run(run(parse_args().query))

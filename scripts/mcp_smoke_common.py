from __future__ import annotations

import json
from datetime import date
from typing import Any


BASE_TOOLS = {
    "resolve_location",
    "find_events",
    "find_places",
    "find_movies",
    "find_movie_showings",
    "find_city_news",
    "find_city_guides",
    "get_details",
}


async def run_smoke(client: Any, query: str) -> None:
    await client.ping()
    tools = await client.list_tools()
    tool_names = {tool.name for tool in tools}
    print("TOOLS:", ", ".join(sorted(tool_names)))
    assert BASE_TOOLS <= tool_names
    assert not {
        "resolve_place",
        "events",
        "places",
        "movies",
        "movie_showings",
        "news",
        "lists",
        "reference",
        "object",
        "transit_route",
        "street_route",
    } & tool_names

    today = date.today().isoformat()
    calls = {
        "resolve_location": {
            "place": query,
            "country_codes": ["ru"],
            "limit": 3,
        },
        "find_events": {
            "location_slug": "msk",
            "date": today,
            "limit": 2,
        },
        "find_places": {"location_slug": "msk", "limit": 2},
        "find_movies": {"location_slug": "msk", "limit": 2},
        "find_movie_showings": {
            "location_slug": "msk",
            "date": today,
            "limit": 2,
        },
        "find_city_news": {"location_slug": "msk", "limit": 2},
        "find_city_guides": {"location_slug": "msk", "limit": 2},
    }
    results: dict[str, Any] = {}
    for tool_name, arguments in calls.items():
        result = await client.call_tool(tool_name, arguments, timeout=60.0)
        results[tool_name] = result.data
        print(f"{tool_name.upper()}:")
        print_result(result.data)
        assert result.data["status"] == "ok"
        assert result.data["tool"] == tool_name
        assert result.data["job_id"]

    event_items = results["find_events"]["data"].get("items", [])
    if event_items and event_items[0].get("details_ref"):
        reference = event_items[0]["details_ref"]
        detail = await client.call_tool("get_details", reference, timeout=60.0)
        print("GET_DETAILS:")
        print_result(detail.data)
        assert detail.data["status"] == "ok"
        assert detail.data["tool"] == "get_details"


def print_result(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


__all__ = ["BASE_TOOLS", "run_smoke"]

import argparse
import asyncio
import json
from typing import Any

from fastmcp import Client


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test MCP tools over HTTP")
    parser.add_argument("query", nargs="?", default="Нахабино")
    parser.add_argument("--url", default="http://127.0.0.1:8011/mcp")
    return parser.parse_args()


def print_result(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


async def run(query: str, url: str) -> None:
    async with Client(url, timeout=60.0) as client:
        await client.ping()
        tools = await client.list_tools()
        tool_names = sorted(tool.name for tool in tools)
        print("TOOLS:", ", ".join(tool_names))
        assert {"events", "lists", "news", "places", "resolve_place"} <= set(
            tool_names
        )

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

        places_result = await client.call_tool(
            "places",
            {"location": "msk", "page_size": 3, "lang": "ru"},
            timeout=60.0,
        )

        news_result = await client.call_tool(
            "news",
            {"location": "msk", "page_size": 3, "lang": "ru"},
            timeout=60.0,
        )
        lists_result = await client.call_tool(
            "lists",
            {"location": "msk", "page_size": 3, "lang": "ru"},
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

    print("PLACES:")
    print_result(places_result.data)
    assert isinstance(places_result.data, dict)
    assert places_result.data["status"] == "ok"
    assert places_result.data["tool"] == "places"
    assert places_result.data["result_status"] == "ok"
    assert places_result.data["data"]["status"] == "ok"

    for tool_name, result in (("news", news_result), ("lists", lists_result)):
        print(f"{tool_name.upper()}:")
        print_result(result.data)
        assert isinstance(result.data, dict)
        assert result.data["status"] == "ok"
        assert result.data["tool"] == tool_name
        assert result.data["result_status"] == "ok"
        assert result.data["data"]["status"] == "ok"


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run(args.query, args.url))

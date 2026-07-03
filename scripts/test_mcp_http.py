import argparse
import asyncio
import json
from typing import Any

from fastmcp import Client


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Call resolve_place over HTTP")
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
        assert "resolve_place" in tool_names

        result = await client.call_tool(
            "resolve_place",
            {
                "query": query,
                "countrycodes": "ru",
                "limit": 5,
                "accept_language": "ru",
            },
            timeout=60.0,
        )

    print_result(result.data)
    assert isinstance(result.data, dict)
    assert result.data["status"] == "ok"
    assert result.data["tool"] == "resolve_place"
    assert result.data["job_id"]


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run(args.query, args.url))

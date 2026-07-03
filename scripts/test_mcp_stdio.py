import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from fastmcp import Client
from fastmcp.client.transports import StdioTransport


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test MCP tools over stdio")
    parser.add_argument("query", nargs="?", default="Нахабино")
    return parser.parse_args()


def subprocess_environment() -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            key: value
            for key, value in dotenv_values(ROOT / ".env").items()
            if value is not None
        }
    )
    return env


def print_result(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


async def run(query: str) -> None:
    transport = StdioTransport(
        command=sys.executable,
        args=[str(ROOT / "mcp_server.py")],
        env=subprocess_environment(),
        cwd=str(ROOT),
        keep_alive=False,
    )

    async with Client(transport, timeout=60.0) as client:
        await client.ping()
        tools = await client.list_tools()
        tool_names = sorted(tool.name for tool in tools)
        print("TOOLS:", ", ".join(tool_names))
        assert "resolve_place" in tool_names

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


if __name__ == "__main__":
    asyncio.run(run(parse_args().query))

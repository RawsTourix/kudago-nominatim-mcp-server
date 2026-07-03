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
    parser = argparse.ArgumentParser(description="Call resolve_place in memory")
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
    asyncio.run(run(parse_args().query))

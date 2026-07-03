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
    parser = argparse.ArgumentParser(description="Call resolve_place over stdio")
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

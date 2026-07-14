import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import dotenv_values
from fastmcp import Client
from fastmcp.client.transports import StdioTransport


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.mcp_smoke_common import run_smoke


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test MCP tools over stdio")
    parser.add_argument("query", nargs="?", default="Нахабино")
    return parser.parse_args()


def subprocess_environment() -> dict[str, str]:
    env = dict(os.environ)
    for key, value in dotenv_values(ROOT / ".env").items():
        if value is not None:
            env.setdefault(key, value)
    return env


async def run(query: str) -> None:
    transport = StdioTransport(
        command=sys.executable,
        args=[str(ROOT / "mcp_server.py")],
        env=subprocess_environment(),
        cwd=str(ROOT),
        keep_alive=False,
    )
    async with Client(transport, timeout=60.0) as client:
        await run_smoke(client, query)


if __name__ == "__main__":
    asyncio.run(run(parse_args().query))

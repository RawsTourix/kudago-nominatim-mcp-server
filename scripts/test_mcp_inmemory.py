import argparse
import asyncio
import sys
from pathlib import Path

from fastmcp import Client


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.mcp.server import create_mcp_server
from scripts.mcp_smoke_common import run_smoke


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test MCP tools in memory")
    parser.add_argument("query", nargs="?", default="Нахабино")
    return parser.parse_args()


async def run(query: str) -> None:
    async with Client(create_mcp_server()) as client:
        await run_smoke(client, query)


if __name__ == "__main__":
    asyncio.run(run(parse_args().query))

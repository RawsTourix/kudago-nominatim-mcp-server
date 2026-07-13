import argparse
import asyncio
import sys
from pathlib import Path

from fastmcp import Client


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.mcp_smoke_common import run_smoke


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test MCP tools over HTTP")
    parser.add_argument("query", nargs="?", default="Нахабино")
    parser.add_argument("--url", default="http://127.0.0.1:8011/mcp")
    return parser.parse_args()


async def run(query: str, url: str) -> None:
    async with Client(url, timeout=60.0) as client:
        await run_smoke(client, query)


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run(args.query, args.url))

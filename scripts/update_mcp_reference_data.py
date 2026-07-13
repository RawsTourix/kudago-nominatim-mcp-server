from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "app" / "mcp" / "reference_data" / "kudago_v1_4.json"
BASE_URL = "https://kudago.com/public-api/v1.4/"
USER_AGENT = "kudago-nominatim-reference-generator/0.1.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh the committed KudaGo v1.4 MCP reference snapshot."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def fetch_reference_data() -> dict[str, Any]:
    with httpx.Client(
        base_url=BASE_URL,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=30.0,
    ) as client:
        event_categories = _fetch_entries(
            client,
            "event-categories/",
            fields="slug,name",
        )
        place_categories = _fetch_entries(
            client,
            "place-categories/",
            fields="slug,name",
        )
        locations = _fetch_entries(
            client,
            "locations/",
            fields="slug,name,timezone",
            include_timezone=True,
        )

    return {
        "api_version": "v1.4",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "event_categories": event_categories,
        "place_categories": place_categories,
        "locations": locations,
    }


def _fetch_entries(
    client: httpx.Client,
    endpoint: str,
    *,
    fields: str,
    include_timezone: bool = False,
) -> list[dict[str, str]]:
    response = client.get(endpoint, params={"lang": "ru", "fields": fields})
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError(f"KudaGo {endpoint} response must be a JSON array")

    entries: list[dict[str, str]] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"KudaGo {endpoint} item {index} must be an object")
        slug = item.get("slug")
        name = item.get("name")
        if not isinstance(slug, str) or not slug.strip():
            raise ValueError(f"KudaGo {endpoint} item {index} has no slug")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"KudaGo {endpoint} item {index} has no name")

        entry = {"slug": slug.strip(), "name": name.strip()}
        if include_timezone:
            timezone_name = item.get("timezone")
            if timezone_name is not None and not isinstance(timezone_name, str):
                raise ValueError(
                    f"KudaGo {endpoint} item {index} has invalid timezone"
                )
            if timezone_name:
                entry["timezone"] = timezone_name
        entries.append(entry)

    entries.sort(key=lambda entry: entry["slug"])
    if len({entry["slug"] for entry in entries}) != len(entries):
        raise ValueError(f"KudaGo {endpoint} contains duplicate slugs")
    return entries


def main() -> None:
    args = parse_args()
    snapshot = fetch_reference_data()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "updated "
        f"{args.output}: "
        f"events={len(snapshot['event_categories'])}, "
        f"places={len(snapshot['place_categories'])}, "
        f"locations={len(snapshot['locations'])}"
    )


if __name__ == "__main__":
    main()

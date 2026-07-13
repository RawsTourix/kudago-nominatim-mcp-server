from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastmcp import Client

from app.mcp.server import create_mcp_server


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "mcp_schemas.json"


async def main() -> None:
    server = create_mcp_server(
        settings_obj=SimpleNamespace(
            transitous_user_agent="schema-inspection/1.0 docs@example.com",
            openrouteservice_api_key="schema-inspection-placeholder",
        )
    )
    async with Client(server) as client:
        tools = await client.list_tools()

    schemas = {
        tool.name: {
            "description": tool.description,
            "inputSchema": tool.inputSchema,
            "annotations": tool.annotations.model_dump(exclude_none=True),
        }
        for tool in tools
    }
    missing = {
        name: _missing_descriptions(data["inputSchema"])
        for name, data in schemas.items()
    }
    missing = {name: paths for name, paths in missing.items() if paths}
    if missing:
        raise SystemExit(f"Missing field descriptions: {missing}")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(schemas, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print("tool | fields | required | enum fields | description coverage")
    print("--- | ---: | --- | --- | ---")
    for name, data in schemas.items():
        schema = data["inputSchema"]
        properties = schema.get("properties", {})
        required = ", ".join(schema.get("required", [])) or "-"
        enum_fields = ", ".join(
            field
            for field, value in properties.items()
            if _has_enum(value, schema)
        ) or "-"
        print(f"{name} | {len(properties)} | {required} | {enum_fields} | 100%")
    print(f"saved {OUTPUT}")


def _missing_descriptions(schema: dict[str, Any], path: str = "") -> list[str]:
    missing: list[str] = []
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for name, subschema in properties.items():
            current = f"{path}.{name}" if path else name
            if not isinstance(subschema, dict) or not subschema.get("description"):
                missing.append(current)
            if isinstance(subschema, dict):
                missing.extend(_missing_descriptions(subschema, current))
    for key in ("items", "anyOf", "oneOf", "allOf"):
        nested = schema.get(key)
        if isinstance(nested, dict):
            missing.extend(_missing_descriptions(nested, path))
        elif isinstance(nested, list):
            for item in nested:
                if isinstance(item, dict):
                    missing.extend(_missing_descriptions(item, path))
    return missing


def _has_enum(
    schema: dict[str, Any],
    root: dict[str, Any] | None = None,
) -> bool:
    root = root or schema
    if schema.get("enum"):
        return True
    reference = schema.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/$defs/"):
        definition = root.get("$defs", {}).get(reference.removeprefix("#/$defs/"))
        if isinstance(definition, dict) and _has_enum(definition, root):
            return True
    if isinstance(schema.get("items"), dict) and _has_enum(schema["items"], root):
        return True
    return any(
        isinstance(item, dict) and _has_enum(item, root)
        for key in ("anyOf", "oneOf", "allOf")
        for item in schema.get(key, [])
    )


if __name__ == "__main__":
    asyncio.run(main())

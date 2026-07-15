from __future__ import annotations

from copy import deepcopy
from typing import Any


def with_exactly_one_routing_time(
    input_schema: dict[str, Any],
) -> dict[str, Any]:
    schema = deepcopy(input_schema)

    properties = schema.get("properties")
    if not isinstance(properties, dict):
        raise ValueError("Tool input schema has no properties object")

    for field in ("departure_time", "arrival_time"):
        if field not in properties:
            raise ValueError(f"Tool input schema is missing {field}")

    if "oneOf" in schema:
        raise ValueError("Tool input schema already contains oneOf")

    non_null_datetime = {
        "type": "string",
        "format": "date-time",
    }
    null_value = {"type": "null"}

    schema["oneOf"] = [
        {
            "title": "Departure-time journey",
            "required": ["departure_time"],
            "properties": {
                "departure_time": non_null_datetime,
                "arrival_time": null_value,
            },
        },
        {
            "title": "Arrival-time journey",
            "required": ["arrival_time"],
            "properties": {
                "arrival_time": non_null_datetime,
                "departure_time": null_value,
            },
        },
    ]

    return schema


__all__ = ["with_exactly_one_routing_time"]

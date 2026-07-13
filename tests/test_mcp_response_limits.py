from app.mcp.serializers.common import (
    ROUTING_RESPONSE_LIMIT_BYTES,
    SEARCH_RESPONSE_LIMIT_BYTES,
    enforce_item_limit,
    json_size,
)


def test_search_items_are_removed_from_end_to_fit_64_kib():
    data = {
        "status": "ok",
        "schedule_verified": True,
        "items": [
            {"id": index, "description": "x" * 20_000}
            for index in range(10)
        ],
    }
    limited = enforce_item_limit(data)
    assert json_size(limited) <= SEARCH_RESPONSE_LIMIT_BYTES
    assert limited["truncated"] is True
    assert limited["full_result_available"] is True
    assert limited["returned_to_agent"] == len(limited["items"])
    assert [item["id"] for item in limited["items"]] == list(
        range(len(limited["items"]))
    )


def test_routing_limit_removes_whole_alternatives_not_legs():
    data = {
        "status": "ok",
        "warnings": [],
        "attribution": [],
        "routes": [
            {"id": index, "legs": [{"description": "x" * 70_000}]}
            for index in range(3)
        ],
    }
    limited = enforce_item_limit(
        data,
        maximum_bytes=ROUTING_RESPONSE_LIMIT_BYTES,
        item_key="routes",
    )
    assert json_size(limited) <= ROUTING_RESPONSE_LIMIT_BYTES
    assert limited["truncated"] is True
    assert all(len(route["legs"]) == 1 for route in limited["routes"])

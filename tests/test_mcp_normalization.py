from copy import deepcopy

from app.mcp.normalization import compact_geo, compact_mcp_data, compact_mcp_meta


def test_compact_geo_removes_raw_nominatim_fields():
    raw_geo = {
        "status": "ambiguous",
        "kind": "none",
        "source": "nominatim",
        "query": "Nakhabino",
        "candidates": [
            {
                "name": "Nakhabino",
                "display_name": "Nakhabino, Moscow Oblast, Russia",
                "type": "town",
                "lat": "55.8394789",
                "lon": "37.1770987",
                "address": {"country": "Russia"},
                "extratags": {"population": "50000"},
                "namedetails": {"name": "Nakhabino", "name:ru": "Нахабино"},
                "boundingbox": ["55.8", "55.9", "37.1", "37.2"],
                "licence": "OpenStreetMap contributors",
            }
        ],
    }

    assert compact_geo(raw_geo) == {
        "status": "ambiguous",
        "kind": "none",
        "source": "nominatim",
        "query": "Nakhabino",
        "candidates": [
            {
                "name": "Nakhabino",
                "display_name": "Nakhabino, Moscow Oblast, Russia",
                "type": "town",
                "lat": "55.8394789",
                "lon": "37.1770987",
            }
        ],
    }


def test_mcp_normalization_does_not_mutate_persisted_output():
    result_payload = {
        "status": "geo_ambiguous",
        "geo": {
            "status": "ambiguous",
            "candidates": [{"lat": "1", "lon": "2", "address": {}}],
        },
        "items": [],
    }
    meta = {"status": "geo_ambiguous", "geo": result_payload["geo"]}
    original_payload = deepcopy(result_payload)
    original_meta = deepcopy(meta)

    data = compact_mcp_data(result_payload)
    compact_meta = compact_mcp_meta(meta)

    assert data["geo"]["candidates"] == [{"lat": "1", "lon": "2"}]
    assert "geo" not in compact_meta
    assert result_payload == original_payload
    assert meta == original_meta


def test_geo_resolve_candidates_are_compacted_in_data():
    data = compact_mcp_data(
        {
            "status": "ambiguous",
            "candidates": [
                {
                    "display_name": "First",
                    "type": "station",
                    "lat": "1",
                    "lon": "2",
                    "extratags": {"railway": "station"},
                }
            ],
        }
    )

    assert data["candidates"] == [
        {
            "display_name": "First",
            "type": "station",
            "lat": "1",
            "lon": "2",
        }
    ]


def test_routing_geometry_and_provider_debug_are_removed_without_mutation():
    result_payload = {
        "status": "ok",
        "provider": "openrouteservice",
        "routes": [
            {
                "distance_meters": 100,
                "geometry": "encoded-polyline",
                "segments": [
                    {
                        "steps": [
                            {
                                "instruction": "Turn left",
                                "name": "Main Street",
                            }
                        ]
                    }
                ],
                "raw_response": {"provider": "debug"},
            }
        ],
        "warnings": ["limited coverage"],
        "attribution": [{"name": "openrouteservice.org"}],
        "debugOutput": {"search_time": 1},
        "requestParameters": {"api_key": "must-not-leak"},
    }
    original = deepcopy(result_payload)

    compact = compact_mcp_data(result_payload)

    route = compact["routes"][0]
    assert "geometry" not in route
    assert route["geometry_hidden"] is True
    assert "raw_response" not in route
    assert route["segments"][0]["steps"][0]["instruction"] == "Turn left"
    assert compact["warnings"] == ["limited coverage"]
    assert compact["attribution"] == [{"name": "openrouteservice.org"}]
    assert "debugOutput" not in compact
    assert "requestParameters" not in compact
    assert result_payload == original

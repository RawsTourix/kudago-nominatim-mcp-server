from app.mcp.reference_data import (
    EventCategory,
    KudaGoLocationSlug,
    PlaceCategory,
    REFERENCE_SNAPSHOT,
)


def test_committed_reference_snapshot_is_sorted_unique_and_versioned():
    assert REFERENCE_SNAPSHOT["api_version"] == "v1.4"
    assert REFERENCE_SNAPSHOT["generated_at"]
    for key in ("event_categories", "place_categories", "locations"):
        slugs = [item["slug"] for item in REFERENCE_SNAPSHOT[key]]
        assert slugs == sorted(slugs)
        assert len(slugs) == len(set(slugs))


def test_reference_enums_match_committed_snapshot():
    assert {item.value for item in EventCategory} == {
        item["slug"] for item in REFERENCE_SNAPSHOT["event_categories"]
    }
    assert {item.value for item in PlaceCategory} == {
        item["slug"] for item in REFERENCE_SNAPSHOT["place_categories"]
    }
    assert {item.value for item in KudaGoLocationSlug} == {
        item["slug"] for item in REFERENCE_SNAPSHOT["locations"]
    }
    assert "museums" in {item.value for item in PlaceCategory}
    assert "museum" not in {item.value for item in PlaceCategory}

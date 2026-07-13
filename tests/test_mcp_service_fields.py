from app.services.events_service import EVENT_SEARCH_FIELDS
from app.services.places_service import PLACE_SEARCH_FIELDS


def test_event_query_requests_fields_used_by_the_agent_serializer():
    assert "description" in EVENT_SEARCH_FIELDS.split(",")


def test_place_query_requests_fields_used_by_the_agent_serializer():
    fields = set(PLACE_SEARCH_FIELDS.split(","))
    assert {"short_title", "description", "timetable", "is_closed"} <= fields

from app.application.executor import HANDLERS


def test_command_registry_contains_all_supported_commands():
    assert set(HANDLERS) == {
        "geo.resolve",
        "events.search",
        "places.search",
        "news.search",
        "lists.search",
        "movies.search",
        "movie_showings.search",
        "reference.get",
        "object.detail",
        "routing.transit.plan",
        "routing.street.plan",
    }

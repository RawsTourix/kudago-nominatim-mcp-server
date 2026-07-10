from app.core.redis import get_redis_settings
from app.workers.tasks import (
    process_events_search_job,
    process_geo_resolve_job,
    process_lists_search_job,
    process_movie_showings_search_job,
    process_movies_search_job,
    process_news_search_job,
    process_places_search_job,
    process_street_routing_job,
    process_test_job,
    process_transit_routing_job,
)


class WorkerSettings:
    functions = [
        process_test_job,
        process_geo_resolve_job,
        process_lists_search_job,
        process_events_search_job,
        process_places_search_job,
        process_movie_showings_search_job,
        process_movies_search_job,
        process_news_search_job,
        process_transit_routing_job,
        process_street_routing_job,
    ]

    redis_settings = get_redis_settings()

    max_jobs = 10
    job_timeout = 120
    keep_result = 3600

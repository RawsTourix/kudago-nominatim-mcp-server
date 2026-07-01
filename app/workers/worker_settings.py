from app.core.redis import get_redis_settings
from app.workers.tasks import process_test_job


class WorkerSettings:
    functions = [
        process_test_job,
    ]

    redis_settings = get_redis_settings()

    max_jobs = 10
    job_timeout = 60
    keep_result = 3600
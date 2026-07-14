from app.core.config import settings
from app.core.redis import get_redis_settings
from app.workers.tasks import (
    process_command_job,
    process_test_job,
)


class WorkerSettings:
    functions = [
        process_test_job,
        process_command_job,
    ]

    redis_settings = get_redis_settings()

    max_jobs = 10
    job_timeout = settings.arq_job_timeout_seconds
    keep_result = 3600

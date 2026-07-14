import inspect
from urllib.parse import urlparse

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import settings


def get_redis_settings(redis_url: str | None = None) -> RedisSettings:
    parsed = urlparse(redis_url or settings.redis_url)

    database = 0
    if parsed.path and parsed.path != "/":
        database = int(parsed.path.lstrip("/"))

    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        database=database,
        password=parsed.password,
    )


async def create_arq_pool(redis_url: str | None = None) -> ArqRedis:
    return await create_pool(get_redis_settings(redis_url))


async def close_arq_pool(redis: ArqRedis) -> None:
    close_func = getattr(redis, "aclose", None) or getattr(redis, "close", None)
    if close_func is None:
        return

    result = close_func()
    if inspect.isawaitable(result):
        await result

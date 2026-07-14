import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/kudago",
)
os.environ.setdefault(
    "TRANSITOUS_USER_AGENT",
    "kudago-nominatim-tests/0.1.0 tests@example.com",
)
os.environ.setdefault(
    "OPENROUTESERVICE_USER_AGENT",
    "kudago-nominatim-tests/0.1.0",
)


@pytest.fixture
def fake_mcp_redis(monkeypatch):
    from app.mcp import server

    redis = SimpleNamespace(name="test-arq-redis")
    create_pool = AsyncMock(return_value=redis)
    close_pool = AsyncMock()
    monkeypatch.setattr(server, "create_arq_pool", create_pool)
    monkeypatch.setattr(server, "close_arq_pool", close_pool)
    return SimpleNamespace(
        redis=redis,
        create_pool=create_pool,
        close_pool=close_pool,
    )

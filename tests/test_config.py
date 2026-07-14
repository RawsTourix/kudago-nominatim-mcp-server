import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_routing_user_agents_do_not_break_existing_environment(monkeypatch):
    monkeypatch.delenv("TRANSITOUS_USER_AGENT", raising=False)
    monkeypatch.delenv("OPENROUTESERVICE_USER_AGENT", raising=False)
    config = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://postgres:postgres@localhost/kudago",
    )

    assert config.transitous_user_agent is None
    assert config.openrouteservice_user_agent == (
        "kudago-nominatim-service/0.1.0"
    )
    assert config.mcp_job_wait_timeout_seconds == 180.0
    assert config.command_job_timeout_seconds == 120.0
    assert config.arq_job_timeout_seconds == 135.0


def test_command_timeout_must_leave_headroom_before_arq_timeout():
    with pytest.raises(
        ValidationError,
        match=(
            "COMMAND_JOB_TIMEOUT_SECONDS must be less than "
            "ARQ_JOB_TIMEOUT_SECONDS"
        ),
    ):
        Settings(
            _env_file=None,
            database_url=(
                "postgresql+asyncpg://postgres:postgres@localhost/kudago"
            ),
            command_job_timeout_seconds=135,
            arq_job_timeout_seconds=135,
        )

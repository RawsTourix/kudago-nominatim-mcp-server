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
    assert config.arq_max_jobs == 10


@pytest.mark.parametrize("arq_timeout", [120.0, 124.999])
def test_command_timeout_must_leave_five_seconds_before_arq_timeout(
    arq_timeout,
):
    with pytest.raises(
        ValidationError,
        match=(
            "ARQ_JOB_TIMEOUT_SECONDS must be at least 5 seconds greater "
            "than COMMAND_JOB_TIMEOUT_SECONDS"
        ),
    ):
        Settings(
            _env_file=None,
            database_url=(
                "postgresql+asyncpg://postgres:postgres@localhost/kudago"
            ),
            command_job_timeout_seconds=120,
            arq_job_timeout_seconds=arq_timeout,
        )


def test_exact_five_second_arq_timeout_headroom_is_valid():
    config = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://postgres:postgres@localhost/kudago",
        command_job_timeout_seconds=120,
        arq_job_timeout_seconds=125,
    )

    assert config.arq_job_timeout_seconds == 125

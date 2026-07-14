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

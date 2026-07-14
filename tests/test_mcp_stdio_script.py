from scripts import test_mcp_stdio


def test_stdio_subprocess_environment_preserves_explicit_values(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://explicit:6379/0")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(
        test_mcp_stdio,
        "dotenv_values",
        lambda path: {
            "REDIS_URL": "redis://from-file:6379/0",
            "DATABASE_URL": "postgresql+asyncpg://from-file/db",
            "EMPTY_VALUE": None,
        },
    )

    env = test_mcp_stdio.subprocess_environment()

    assert env["REDIS_URL"] == "redis://explicit:6379/0"
    assert env["DATABASE_URL"] == "postgresql+asyncpg://from-file/db"
    assert "EMPTY_VALUE" not in env

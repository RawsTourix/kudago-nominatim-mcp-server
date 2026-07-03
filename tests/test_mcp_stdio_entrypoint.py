import os

from app.mcp.__main__ import prepare_stdio_environment


def test_stdio_entrypoint_disables_database_echo(monkeypatch):
    monkeypatch.setenv("DATABASE_ECHO", "1")

    prepare_stdio_environment()

    assert os.environ["DATABASE_ECHO"] == "0"

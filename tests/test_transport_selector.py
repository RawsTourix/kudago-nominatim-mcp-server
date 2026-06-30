from __future__ import annotations

from kudago_nominatim_config import Settings

# Importing server requires mcp package. This test intentionally targets pure helpers only.
# The server transport selector is syntax-checked by compileall.


def test_settings_transport_defaults() -> None:
    settings = Settings()
    assert settings.mcp_transport == "stdio"
    assert settings.mcp_host == "127.0.0.1"
    assert settings.mcp_port == 8010
    assert settings.mcp_path == "/mcp/"

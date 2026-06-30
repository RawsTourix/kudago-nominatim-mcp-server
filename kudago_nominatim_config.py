from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None  # type: ignore[assignment]


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings for the KudaGo + Nominatim MCP server."""

    kudago_base_url: str = "https://kudago.com/public-api/v1.4/"
    nominatim_base_url: str = "https://nominatim.openstreetmap.org/"
    nominatim_user_agent: str = "kudago-nominatim-mcp/0.1.0"
    nominatim_referer: str | None = None
    nominatim_email: str | None = None
    nominatim_min_interval_seconds: float = 1.0
    default_lang: str = "ru"
    default_countrycodes: str = "ru"
    default_radius: int = 50_000
    log_dir: str = "logging"
    trust_env: bool = True

    mcp_transport: str = "stdio"
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8010
    mcp_path: str = "/mcp/"


DEFAULT_SETTINGS = Settings()


def bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_settings(env_file: str | Path | None = None) -> Settings:
    """Load settings from environment and optional .env file."""

    if load_dotenv is not None:
        load_dotenv(dotenv_path=env_file)

    return Settings(
        kudago_base_url=os.getenv("KUDAGO_BASE_URL", DEFAULT_SETTINGS.kudago_base_url),
        nominatim_base_url=os.getenv("NOMINATIM_BASE_URL", DEFAULT_SETTINGS.nominatim_base_url),
        nominatim_user_agent=os.getenv("NOMINATIM_USER_AGENT", DEFAULT_SETTINGS.nominatim_user_agent),
        nominatim_referer=os.getenv("NOMINATIM_REFERER") or None,
        nominatim_email=os.getenv("NOMINATIM_EMAIL") or None,
        nominatim_min_interval_seconds=float(os.getenv("NOMINATIM_MIN_INTERVAL_SECONDS", str(DEFAULT_SETTINGS.nominatim_min_interval_seconds))),
        default_lang=os.getenv("KUDAGO_LANG", DEFAULT_SETTINGS.default_lang),
        default_countrycodes=os.getenv("NOMINATIM_COUNTRYCODES", DEFAULT_SETTINGS.default_countrycodes),
        default_radius=int(os.getenv("DEFAULT_RADIUS", str(DEFAULT_SETTINGS.default_radius))),
        log_dir=os.getenv("LOG_DIR", DEFAULT_SETTINGS.log_dir),
        trust_env=bool_env("TRUST_ENV", DEFAULT_SETTINGS.trust_env),
        mcp_transport=os.getenv("MCP_TRANSPORT", DEFAULT_SETTINGS.mcp_transport),
        mcp_host=os.getenv("MCP_HOST", DEFAULT_SETTINGS.mcp_host),
        mcp_port=int(os.getenv("MCP_PORT", str(DEFAULT_SETTINGS.mcp_port))),
        mcp_path=os.getenv("MCP_PATH", DEFAULT_SETTINGS.mcp_path),
    )

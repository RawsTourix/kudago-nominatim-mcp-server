from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


MIN_ARQ_TIMEOUT_HEADROOM_SECONDS = 5.0


class Settings(BaseSettings):
    app_name: str = "KudaGo FastAPI Service"
    debug: bool = False
    database_echo: bool = False

    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    command_job_timeout_seconds: float = Field(default=120.0, gt=0)
    arq_job_timeout_seconds: float = Field(default=135.0, gt=0)
    arq_max_jobs: int = Field(default=10, ge=1)
    mcp_job_wait_timeout_seconds: float = Field(default=180.0, gt=0)

    kudago_base_url: str = "https://kudago.com/public-api/v1.4/"
    kudago_lang: str = "ru"
    kudago_user_agent: str = "kudago-fastapi-service/0.1.0"

    nominatim_user_agent: str = "kudago-fastapi-service/0.1.0"
    nominatim_min_interval_seconds: float = 1.0
    nominatim_countrycodes: str = "ru"
    default_radius: int = 50_000

    transitous_base_url: str = "https://api.transitous.org/"
    transitous_user_agent: str | None = None
    transitous_timeout_seconds: float = 40.0

    openrouteservice_base_url: str = "https://api.openrouteservice.org/"
    openrouteservice_api_key: str | None = None
    openrouteservice_user_agent: str = "kudago-nominatim-service/0.1.0"
    openrouteservice_timeout_seconds: float = 30.0

    @model_validator(mode="after")
    def validate_job_timeouts(self) -> "Settings":
        headroom = (
            self.arq_job_timeout_seconds - self.command_job_timeout_seconds
        )
        if headroom < MIN_ARQ_TIMEOUT_HEADROOM_SECONDS:
            raise ValueError(
                "ARQ_JOB_TIMEOUT_SECONDS must be at least 5 seconds greater "
                "than COMMAND_JOB_TIMEOUT_SECONDS"
            )
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

from functools import lru_cache
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    # Application settings
    app_name: str = Field(default="IncuBrix Distribution Engine", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    debug: bool = Field(default=False, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # MongoDB settings
    mongodb_uri: str = Field(default="mongodb://localhost:27017", alias="MONGODB_URI")
    mongodb_db_name: str = Field(default="incubrix", alias="MONGODB_DB_NAME")
    mongodb_timeout_ms: int = Field(default=2000, alias="MONGODB_TIMEOUT_MS")

    # Security settings
    secret_key: str = Field(
        default="development-only-secret-key-change-in-production",
        alias="SECRET_KEY",
    )

    # Simulation & Security settings
    simulation_mode: bool = Field(default=True, alias="SIMULATION_MODE")
    allow_local_destinations: bool = Field(default=False, alias="ALLOW_LOCAL_DESTINATIONS")
    discourse_test_url: Optional[str] = Field(default=None, alias="DISCOURSE_TEST_URL")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()

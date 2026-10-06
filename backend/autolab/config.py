"""App settings, read from environment variables and `.env`."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    # Separate database for pytest; the tests never use database_url.
    test_database_url: str | None = None

    # Auth. jwt_secret is checked when the API starts (auth step).
    jwt_secret: str = ""
    access_token_minutes: int = 15
    refresh_token_days: int = 30

    # Log store for full LLM prompts and outputs.
    log_store: Literal["mongo", "file"] = "file"
    mongo_url: str = "mongodb://localhost:27017"
    mongo_db: str = "autolab"

    # Search service (SearxNG, JSON API) and page downloads
    searxng_url: str = "http://localhost:8888"
    fetch_user_agent: str = "AutoLab/0.1 (research assistant)"

    # Worker
    worker_poll_seconds: float = 3.0  # wait between checks for queued tasks
    log_cleanup_seconds: float = 300.0
    llm_timeout_seconds: float = 300.0  # small GPU: one call can be slow

    data_dir: str = "data"
    max_upload_bytes: int = 50 * 1024 * 1024  # one workspace file
    pipelines_dir: str = "pipelines"
    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()

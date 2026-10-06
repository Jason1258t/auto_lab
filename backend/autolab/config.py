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

    data_dir: str = "data"
    pipelines_dir: str = "pipelines"
    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()

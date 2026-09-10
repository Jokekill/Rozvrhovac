"""Application settings, loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "School Timetable Optimizer"
    database_url: str = "postgresql+psycopg://timetable:timetable@localhost:5432/timetable"
    redis_url: str = "redis://localhost:6379/0"

    # When true the solver job runs synchronously in the API process.
    # Useful for tests and for a Redis-less local run.
    run_solver_inline: bool = False

    # disabled | oidc  (see app/api/deps.py)
    auth_mode: str = "disabled"
    oidc_issuer: str | None = None
    oidc_audience: str | None = None

    default_solver_time_limit: int = 60
    solver_workers: int = 8

    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

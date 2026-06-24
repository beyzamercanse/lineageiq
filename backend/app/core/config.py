"""Application configuration loaded from environment / .env.

All settings are typed. Money/time policy and determinism seed live here so the whole app shares
one source of truth.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root: backend/app/core/config.py -> parents[3]. Used to anchor data/artifact paths so the
# app works regardless of the current working directory (e.g. uvicorn launched from backend/).
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Typed application settings."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # App
    lineageiq_env: str = Field(default="local", alias="LINEAGEIQ_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Database (default SQLite path is anchored to the repo root, not the cwd)
    database_url: str = Field(
        default=f"sqlite:///{PROJECT_ROOT / 'data' / 'generated' / 'lineageiq.db'}",
        alias="DATABASE_URL",
    )
    database_url_ro: str | None = Field(default=None, alias="DATABASE_URL_RO")

    # Determinism
    random_seed: int = Field(default=20240601, alias="RANDOM_SEED")

    # LLM
    llm_provider: str = Field(default="fake", alias="LLM_PROVIDER")
    llm_model: str = Field(default="claude-fake-1", alias="LLM_MODEL")
    llm_api_key: str | None = Field(default=None, alias="LLM_API_KEY")
    llm_base_url: str | None = Field(default=None, alias="LLM_BASE_URL")
    llm_input_cost_per_1k: float = Field(default=0.0, alias="LLM_INPUT_COST_PER_1K")
    llm_output_cost_per_1k: float = Field(default=0.0, alias="LLM_OUTPUT_COST_PER_1K")

    # Agent budgets
    agent_max_tool_calls: int = Field(default=8, alias="AGENT_MAX_TOOL_CALLS")
    agent_max_sql_retries: int = Field(default=2, alias="AGENT_MAX_SQL_RETRIES")
    agent_max_duration_seconds: int = Field(default=120, alias="AGENT_MAX_DURATION_SECONDS")
    agent_max_tokens: int = Field(default=20000, alias="AGENT_MAX_TOKENS")
    agent_cost_ceiling_usd: float = Field(default=1.0, alias="AGENT_COST_CEILING_USD")

    # SQL tool limits
    sql_row_limit: int = Field(default=200, alias="SQL_ROW_LIMIT")
    sql_timeout_seconds: int = Field(default=5, alias="SQL_TIMEOUT_SECONDS")
    sql_max_query_length: int = Field(default=4000, alias="SQL_MAX_QUERY_LENGTH")

    # Observability
    otel_enabled: bool = Field(default=False, alias="OTEL_ENABLED")
    otel_exporter_otlp_endpoint: str = Field(
        default="http://localhost:4317", alias="OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    otel_service_name: str = Field(default="lineageiq-backend", alias="OTEL_SERVICE_NAME")

    # Data versioning
    dataset_version: str = Field(default="v1", alias="DATASET_VERSION")

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgres")


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()

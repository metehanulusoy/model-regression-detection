"""Runtime configuration. All values overridable via environment variables."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Singleton-style settings, populated from env or .env file."""

    model_config = SettingsConfigDict(
        env_prefix="MRD_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = Field(default="", description="OpenAI API key")
    openai_base_url: str = Field(default="https://api.openai.com/v1")

    target_model: str = Field(default="gpt-4o-mini", description="Model under test")
    judge_model: str = Field(default="gpt-4o", description="LLM-as-judge model")

    db_path: Path = Field(default=Path("./mrd.sqlite3"))
    prompts_dir: Path = Field(default=Path("./prompts"))
    golden_dir: Path = Field(default=Path("./golden"))
    reports_dir: Path = Field(default=Path("./reports"))

    max_concurrency: int = Field(default=10, ge=1, le=100)
    request_timeout_s: float = Field(default=60.0, gt=0)
    max_retries: int = Field(default=3, ge=0, le=10)

    warning_delta_pct: float = Field(default=3.0, ge=0)
    critical_delta_pct: float = Field(default=8.0, ge=0)
    drift_window: int = Field(default=7, ge=2)

    slack_webhook_url: str = Field(default="")
    github_token: str = Field(default="")
    github_repository: str = Field(default="")
    github_pr_number: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _check_thresholds(self) -> Settings:
        if self.critical_delta_pct < self.warning_delta_pct:
            raise ValueError("critical_delta_pct must be >= warning_delta_pct")
        return self


def load_settings(**overrides: object) -> Settings:
    """Build a Settings instance, with explicit overrides taking precedence."""
    return Settings(**overrides)  # type: ignore[arg-type]

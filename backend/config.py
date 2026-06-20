"""Tradi configuration."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent
ELIGIBLE_TOKENS_PATH = ROOT_DIR / "ELIGIBLE_TOKENS.json"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # TWAK
    twak_access_id: str = ""
    twak_hmac_secret: str = ""
    twak_agent_password: str = ""

    # Data providers
    cmc_api_key: str = ""
    bnb_sdk_api_key: str = ""

    # Agent
    agent_mode: Literal["competition", "paper", "live"] = "paper"
    competition_start: str = "2026-06-22T00:00:00Z"
    competition_end: str = "2026-06-28T23:59:59Z"

    # Risk
    max_drawdown_halt: float = 0.25
    max_drawdown_dq: float = 0.30
    daily_loss_halt: float = 0.10
    max_position_pct: float = 0.25
    max_trades_per_day: int = 5
    max_concurrent_positions: int = 3

    # Database
    database_url: str = "sqlite+aiosqlite:///./tradi.db"

    # API
    api_secret: str = "dev-secret"
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    # Optional
    arkham_api_key: str = ""
    nansen_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()

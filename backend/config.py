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
    cmc_mcp_api_key: str = ""

    # x402 micropayments (CMC premium MCP endpoints — USDC on Base via TWAK)
    x402_enabled: bool = False
    x402_max_payment_usdc: float = 0.01

    # Agent
    agent_mode: Literal["competition", "paper", "live"] = "paper"
    competition_dry_run: bool = False
    competition_start: str = "2026-06-22T00:00:00Z"
    competition_end: str = "2026-06-28T23:59:59Z"
    competition_auto_switch: bool = True

    # Risk
    max_drawdown_halt: float = 0.25
    max_drawdown_dq: float = 0.30
    daily_loss_halt: float = 0.05
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

    # Advisory gate (veto-only external review, fail-open)
    advisory_gate_enabled: bool = False
    advisory_gate_api_key: str = ""
    openai_api_key: str = ""
    advisory_gate_model: str = "gpt-3.5-turbo"


@lru_cache
def get_settings() -> Settings:
    return Settings()

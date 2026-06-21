"""Tournament mode configuration loader."""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TOURNAMENT_PATH = ROOT_DIR / "config" / "tournament_week.yaml"
DEFAULT_PRODUCTION_PATH = ROOT_DIR / "config" / "production.yaml"


@dataclass
class TournamentConfig:
    strategy: str = "momentum_pullback_v3"
    asymmetric_exits: str = "1.5:6.0"
    adx_filter: float = 30.0
    sizing: str = "aggressive"
    universe: str = "top_20_momentum"
    halt_drawdown: float = 0.20
    daily_loss_limit: float = 0.05
    enforcer_enabled: bool = True
    forced_size: float = 0.005
    forced_time: str = "20:00"
    top_n_tokens: int = 20
    min_atr_pct: float = 0.0
    max_gas_gwei: float = 0.0  # 0 = disabled; strategy entries deferred above this

    stop_loss_pct: float = field(init=False)
    take_profit_pct: float = field(init=False)
    enforcer_hour: int = field(init=False)

    def __post_init__(self) -> None:
        parts = self.asymmetric_exits.split(":")
        self.stop_loss_pct = float(parts[0]) / 100 if parts else 0.015
        self.take_profit_pct = float(parts[1]) / 100 if len(parts) > 1 else 0.06
        hour_str = self.forced_time.split(":")[0]
        self.enforcer_hour = int(hour_str)


def load_tournament_config(path: Optional[Path] = None) -> TournamentConfig:
    config_path = path or DEFAULT_TOURNAMENT_PATH
    if not config_path.exists():
        raise FileNotFoundError(f"Tournament config not found: {config_path}")

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    risk = raw.get("risk", {})
    enforcer = raw.get("enforcer", {})
    strategy_block = raw.get("strategy")
    min_atr_pct = 0.0
    if isinstance(strategy_block, dict):
        min_atr_pct = float(strategy_block.get("min_atr_pct", 0))
    min_atr_pct = float(raw.get("min_atr_pct", min_atr_pct))

    execution = raw.get("execution", {})
    max_gas_gwei = float(execution.get("max_gas_gwei", raw.get("max_gas_gwei", 0)))

    return TournamentConfig(
        strategy=raw.get("strategy", "momentum_pullback_v3")
        if not isinstance(strategy_block, dict)
        else strategy_block.get("name", "momentum_pullback_v3"),
        asymmetric_exits=raw.get("asymmetric_exits", "1.5:6.0"),
        adx_filter=float(raw.get("adx_filter", 30)),
        sizing=raw.get("sizing", "aggressive"),
        universe=raw.get("universe", "top_20_momentum"),
        halt_drawdown=float(risk.get("halt_drawdown", 0.20)),
        daily_loss_limit=float(risk.get("daily_loss_limit", 0.05)),
        enforcer_enabled=bool(enforcer.get("enabled", True)),
        forced_size=float(enforcer.get("forced_size", 0.005)),
        forced_time=enforcer.get("forced_time", "20:00"),
        min_atr_pct=min_atr_pct,
        max_gas_gwei=max_gas_gwei,
    )


def load_agent_config(path: Optional[Path] = None) -> TournamentConfig:
    return load_tournament_config(path)

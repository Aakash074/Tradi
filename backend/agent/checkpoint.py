"""Agent session checkpoint — survive restarts on laptop."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from config import ROOT_DIR

if TYPE_CHECKING:
    from agent.orchestrator import TradiOrchestrator

logger = logging.getLogger(__name__)

CHECKPOINT_VERSION = 1
DEFAULT_CHECKPOINT_PATH = ROOT_DIR / "data" / "agent_checkpoint.json"


def _config_path_str(path: Optional[Path]) -> str:
    if path is None:
        return ""
    try:
        return str(path.resolve())
    except OSError:
        return str(path)


def build_checkpoint(orch: "TradiOrchestrator", cycle_num: int) -> dict[str, Any]:
    s = orch.portfolio.state
    return {
        "version": CHECKPOINT_VERSION,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "cycle_num": cycle_num,
        "agent_mode": orch.settings.agent_mode,
        "competition_dry_run": orch.settings.competition_dry_run,
        "config_path": _config_path_str(orch.tournament_config_path),
        "open_positions": list(orch._open_positions),
        "portfolio": {
            "total_value_usd": s.total_value_usd,
            "initial_value_usd": s.initial_value_usd,
            "peak_value_usd": s.peak_value_usd,
            "cash_usd": s.cash_usd,
            "positions_value_usd": s.positions_value_usd,
            "day_start_value_usd": s.day_start_value_usd,
            "trades_today": s.trades_today,
            "consecutive_losses": s.consecutive_losses,
            "last_trade_date": s.last_trade_date,
            "realized_pnl_usd": s.realized_pnl_usd,
            "wallet_synced": s.wallet_synced,
            "holdings": dict(s.holdings),
        },
        "last_kelly_size": orch._last_kelly_size,
    }


def _compatible(orch: "TradiOrchestrator", data: dict[str, Any]) -> bool:
    if data.get("version") != CHECKPOINT_VERSION:
        return False
    if data.get("agent_mode") != orch.settings.agent_mode:
        return False
    if bool(data.get("competition_dry_run")) != bool(orch.settings.competition_dry_run):
        return False
    saved_cfg = data.get("config_path") or ""
    current_cfg = _config_path_str(orch.tournament_config_path)
    if saved_cfg and current_cfg and saved_cfg != current_cfg:
        return False
    return True


def save_checkpoint(
    orch: "TradiOrchestrator",
    cycle_num: int,
    path: Path = DEFAULT_CHECKPOINT_PATH,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_checkpoint(orch, cycle_num)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    tmp.replace(path)
    logger.debug(
        "CHECKPOINT saved cycle=%d positions=%d trades_today=%d",
        cycle_num,
        len(orch._open_positions),
        orch.portfolio.state.trades_today,
    )


def load_checkpoint(
    orch: "TradiOrchestrator",
    path: Path = DEFAULT_CHECKPOINT_PATH,
) -> bool:
    """Restore session state. Returns True if a compatible checkpoint was applied."""
    if not path.exists():
        return False

    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("CHECKPOINT load failed (corrupt file): %s", e)
        return False

    if not _compatible(orch, data):
        logger.info(
            "CHECKPOINT skipped — mode/config mismatch (saved %s/%s, now %s/%s)",
            data.get("agent_mode"),
            data.get("config_path", "?"),
            orch.settings.agent_mode,
            _config_path_str(orch.tournament_config_path) or "?",
        )
        return False

    pf = data.get("portfolio") or {}
    orch.portfolio.load_state_dict(pf)
    orch._open_positions = list(data.get("open_positions") or [])
    orch._last_kelly_size = float(data.get("last_kelly_size") or 0.0)
    orch._checkpoint_cycle_num = int(data.get("cycle_num") or 0)

    orch.trade_enforcer.sync_from_portfolio(orch.portfolio.state.trades_today)
    orch.portfolio.mark_to_market(orch._open_positions)
    drawdown = orch.portfolio.state.drawdown_pct
    orch.confluence.russian_doll.check_drawdown(drawdown)

    logger.info(
        "CHECKPOINT restored %d positions, trades_today=%d, cycle=%d (saved %s)",
        len(orch._open_positions),
        orch.portfolio.state.trades_today,
        orch._checkpoint_cycle_num,
        data.get("saved_at", "?"),
    )
    return True

"""Ghost position tracker — shadow book for signal validation."""

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class GhostTracker:
    """Tracks paper trades for all signals to validate edge in real-time."""

    MIN_GHOST_WIN_RATE = 0.52
    MIN_SIGNAL_STRENGTH = 0.7
    LOOKBACK = 50

    def __init__(self):
        self.ghost_book: list[dict] = []
        self.real_trades: list[dict] = []

    def log_ghost(self, token: str, entry_price: float, signal_strength: float, strategy: str) -> None:
        self.ghost_book.append({
            "token": token,
            "entry_price": entry_price,
            "signal_strength": signal_strength,
            "strategy": strategy,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "theoretical": True,
            "exit_price": None,
            "pnl_pct": None,
        })
        if len(self.ghost_book) > 500:
            self.ghost_book = self.ghost_book[-500:]

    def resolve_ghost(self, token: str, exit_price: float) -> None:
        for ghost in reversed(self.ghost_book):
            if ghost["token"] == token and ghost["exit_price"] is None:
                entry = ghost["entry_price"]
                ghost["exit_price"] = exit_price
                ghost["pnl_pct"] = (exit_price - entry) / entry if entry else 0
                break

    def get_last_n_ghosts(self, n: int = 50) -> list[dict]:
        resolved = [g for g in self.ghost_book if g.get("pnl_pct") is not None]
        return resolved[-n:]

    def calculate_win_rate(self, ghosts: Optional[list[dict]] = None) -> float:
        ghosts = ghosts or self.get_last_n_ghosts(self.LOOKBACK)
        if not ghosts:
            return 0.55  # optimistic prior for cold start
        wins = sum(1 for g in ghosts if (g.get("pnl_pct") or 0) > 0)
        return wins / len(ghosts)

    def evaluate_signal(self, token: str, signal_strength: float, entry_price: float, strategy: str) -> str:
        self.log_ghost(token, entry_price, signal_strength, strategy)
        ghost_win_rate = self.calculate_win_rate()
        if ghost_win_rate > self.MIN_GHOST_WIN_RATE and signal_strength > self.MIN_SIGNAL_STRENGTH:
            return "EXECUTE"
        return "OBSERVE"

    def log_real_trade(self, trade: dict) -> None:
        self.real_trades.append(trade)

    def get_stats(self) -> dict:
        ghosts = self.get_last_n_ghosts(self.LOOKBACK)
        ghost_pnl = sum(g.get("pnl_pct", 0) or 0 for g in ghosts)
        real_pnl = sum(t.get("pnl_pct", 0) or 0 for t in self.real_trades[-self.LOOKBACK:])
        return {
            "ghost_count": len(ghosts),
            "ghost_win_rate": round(self.calculate_win_rate(ghosts) * 100, 1),
            "ghost_cumulative_pnl_pct": round(ghost_pnl * 100, 2),
            "real_cumulative_pnl_pct": round(real_pnl * 100, 2),
            "real_trade_count": len(self.real_trades),
        }

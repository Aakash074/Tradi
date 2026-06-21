"""Portfolio tracking and PnL calculations."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class PortfolioState:
    total_value_usd: float = 10_000.0
    initial_value_usd: float = 10_000.0
    peak_value_usd: float = 10_000.0
    cash_usd: float = 10_000.0
    positions_value_usd: float = 0.0
    drawdown_pct: float = 0.0
    daily_pnl_pct: float = 0.0
    total_return_pct: float = 0.0
    unrealized_pnl_usd: float = 0.0
    unrealized_pnl_pct: float = 0.0
    realized_pnl_usd: float = 0.0
    day_start_value_usd: float = 10_000.0
    trades_today: int = 0
    consecutive_losses: int = 0
    last_trade_date: Optional[str] = None
    wallet_synced: bool = False
    holdings: dict[str, float] = field(default_factory=dict)


class PortfolioTracker:
    def __init__(self, initial_value: float = 10_000.0):
        self.state = PortfolioState(
            total_value_usd=initial_value,
            initial_value_usd=initial_value,
            peak_value_usd=initial_value,
            cash_usd=initial_value,
            day_start_value_usd=initial_value,
        )

    def seed_from_wallet(self, wallet_usd: float) -> None:
        """Replace paper seed with on-chain wallet valuation."""
        self.state.cash_usd = wallet_usd
        self.state.initial_value_usd = wallet_usd
        self.state.total_value_usd = wallet_usd
        self.state.peak_value_usd = wallet_usd
        self.state.day_start_value_usd = wallet_usd
        self.state.positions_value_usd = 0.0
        self.state.unrealized_pnl_usd = 0.0
        self.state.unrealized_pnl_pct = 0.0
        self.state.realized_pnl_usd = 0.0
        self.state.holdings = {}
        self.state.wallet_synced = True
        self._recompute_metrics(wallet_usd)

    def allocate_cash(self, amount_usd: float, token: str) -> bool:
        if amount_usd <= 0 or amount_usd > self.state.cash_usd + 1e-6:
            return False
        self.state.cash_usd -= amount_usd
        self.state.holdings[token] = self.state.holdings.get(token, 0.0) + amount_usd
        return True

    @staticmethod
    def position_market_value(pos: dict) -> float:
        amount = pos.get("amount_usd") or 0.0
        entry = pos.get("entry_price") or 0.0
        current = pos.get("current_price") or entry
        if amount <= 0:
            return 0.0
        if entry > 0:
            return amount * (current / entry)
        return amount

    def positions_market_value(self, open_positions: list[dict]) -> float:
        return sum(self.position_market_value(p) for p in open_positions)

    def close_position(
        self,
        amount_usd: float,
        entry_price: float,
        exit_price: float,
        token: str,
    ) -> tuple[float, float]:
        """Release position to cash. Returns (realized_pnl_usd, realized_pnl_pct)."""
        if amount_usd <= 0:
            return 0.0, 0.0

        if entry_price > 0:
            proceeds = amount_usd * (exit_price / entry_price)
            pnl_usd = proceeds - amount_usd
            pnl_pct = (exit_price - entry_price) / entry_price
        else:
            proceeds = amount_usd
            pnl_usd = 0.0
            pnl_pct = 0.0

        self.state.cash_usd += proceeds
        self.state.realized_pnl_usd += pnl_usd
        self._adjust_holdings(token, amount_usd)
        self._record_close(pnl_usd)
        return pnl_usd, pnl_pct

    def trim_position(
        self,
        trim_usd: float,
        entry_price: float,
        exit_price: float,
        token: str,
    ) -> float:
        """Partial exit (profit protection). Returns realized pnl on trimmed slice."""
        if trim_usd <= 0:
            return 0.0
        pnl_usd, _ = self.close_position(trim_usd, entry_price, exit_price, token)
        return pnl_usd

    def _adjust_holdings(self, token: str, amount_usd: float) -> None:
        if token not in self.state.holdings:
            return
        self.state.holdings[token] = max(0.0, self.state.holdings[token] - amount_usd)
        if self.state.holdings[token] <= 1e-9:
            del self.state.holdings[token]

    def mark_to_market(self, open_positions: list[dict]) -> None:
        """Valuation: cash + sum(position market values)."""
        positions_value = self.positions_market_value(open_positions)
        cost_basis = sum(p.get("amount_usd") or 0.0 for p in open_positions)
        total = self.state.cash_usd + positions_value

        self.state.positions_value_usd = positions_value
        self.state.unrealized_pnl_usd = positions_value - cost_basis
        self.state.unrealized_pnl_pct = (
            (positions_value - cost_basis) / cost_basis if cost_basis > 0 else 0.0
        )
        self._recompute_metrics(total)

    def _recompute_metrics(self, total_value: float) -> None:
        self.state.total_value_usd = total_value
        if total_value > self.state.peak_value_usd:
            self.state.peak_value_usd = total_value
        if self.state.peak_value_usd > 0:
            self.state.drawdown_pct = (
                self.state.peak_value_usd - total_value
            ) / self.state.peak_value_usd
        if self.state.initial_value_usd > 0:
            self.state.total_return_pct = (
                total_value - self.state.initial_value_usd
            ) / self.state.initial_value_usd
        if self.state.day_start_value_usd > 0:
            self.state.daily_pnl_pct = (
                total_value - self.state.day_start_value_usd
            ) / self.state.day_start_value_usd

    def update_value(self, total_value: float) -> None:
        """Legacy hook — prefer mark_to_market()."""
        self._recompute_metrics(total_value)

    def record_entry(self) -> None:
        """Count a new position opened today."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.state.last_trade_date != today:
            self.state.trades_today = 0
            self.state.day_start_value_usd = self.state.total_value_usd
            self.state.last_trade_date = today
        self.state.trades_today += 1

    def _record_close(self, pnl_usd: float) -> None:
        if pnl_usd < 0:
            self.state.consecutive_losses += 1
        else:
            self.state.consecutive_losses = 0

    def record_trade(self, pnl_usd: float) -> None:
        """Legacy alias — records a close outcome."""
        self._record_close(pnl_usd)

    def reset_daily(self) -> None:
        self.state.day_start_value_usd = self.state.total_value_usd
        self.state.trades_today = 0
        self.state.daily_pnl_pct = 0.0

    def to_dict(self) -> dict:
        return {
            "total_value_usd": round(self.state.total_value_usd, 2),
            "initial_value_usd": round(self.state.initial_value_usd, 2),
            "peak_value_usd": round(self.state.peak_value_usd, 2),
            "cash_usd": round(self.state.cash_usd, 2),
            "positions_value_usd": round(self.state.positions_value_usd, 2),
            "drawdown_pct": round(self.state.drawdown_pct * 100, 2),
            "daily_pnl_pct": round(self.state.daily_pnl_pct * 100, 2),
            "total_return_pct": round(self.state.total_return_pct * 100, 2),
            "unrealized_pnl_usd": round(self.state.unrealized_pnl_usd, 2),
            "unrealized_pnl_pct": round(self.state.unrealized_pnl_pct * 100, 2),
            "realized_pnl_usd": round(self.state.realized_pnl_usd, 2),
            "trades_today": self.state.trades_today,
            "consecutive_losses": self.state.consecutive_losses,
            "wallet_synced": self.state.wallet_synced,
            "holdings": self.state.holdings,
        }

    def load_state_dict(self, data: dict) -> None:
        """Restore portfolio fields from checkpoint (fractions, not dashboard %)."""
        s = self.state
        for key in (
            "total_value_usd",
            "initial_value_usd",
            "peak_value_usd",
            "cash_usd",
            "positions_value_usd",
            "day_start_value_usd",
            "realized_pnl_usd",
        ):
            if key in data:
                setattr(s, key, float(data[key]))
        if "trades_today" in data:
            s.trades_today = int(data["trades_today"])
        if "consecutive_losses" in data:
            s.consecutive_losses = int(data["consecutive_losses"])
        if "last_trade_date" in data:
            s.last_trade_date = data["last_trade_date"]
        if "wallet_synced" in data:
            s.wallet_synced = bool(data["wallet_synced"])
        if "holdings" in data:
            s.holdings = dict(data["holdings"])

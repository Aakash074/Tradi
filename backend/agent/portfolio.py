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
    drawdown_pct: float = 0.0
    daily_pnl_pct: float = 0.0
    total_return_pct: float = 0.0
    day_start_value_usd: float = 10_000.0
    trades_today: int = 0
    consecutive_losses: int = 0
    last_trade_date: Optional[str] = None
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

    def update_value(self, total_value: float) -> None:
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

    def record_trade(self, pnl_usd: float) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.state.last_trade_date != today:
            self.state.trades_today = 0
            self.state.day_start_value_usd = self.state.total_value_usd
            self.state.last_trade_date = today
        self.state.trades_today += 1
        if pnl_usd < 0:
            self.state.consecutive_losses += 1
        else:
            self.state.consecutive_losses = 0

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
            "drawdown_pct": round(self.state.drawdown_pct * 100, 2),
            "daily_pnl_pct": round(self.state.daily_pnl_pct * 100, 2),
            "total_return_pct": round(self.state.total_return_pct * 100, 2),
            "trades_today": self.state.trades_today,
            "consecutive_losses": self.state.consecutive_losses,
            "holdings": self.state.holdings,
        }

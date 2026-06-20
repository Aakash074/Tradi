"""Smart daily trade enforcer — tournament-aware qualification trades."""

import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from strategies.signal_generation import TradeSignal
from tournament_config import TournamentConfig

logger = logging.getLogger(__name__)

ScanFn = Callable[[], Awaitable[list[TradeSignal]]]
ExecuteFn = Callable[[TradeSignal], Awaitable[Optional[dict]]]
SafestTokenFn = Callable[[], Awaitable[Optional[str]]]


class SmartTradeEnforcer:
    """Force a minimal daily qualification trade after configured UTC hour."""

    def __init__(self, tournament: Optional[TournamentConfig] = None):
        self.tournament = tournament
        self.enabled = tournament.enforcer_enabled if tournament else True
        self.enforce_hour = tournament.enforcer_hour if tournament else 20
        self.qualification_size = tournament.forced_size if tournament else 0.005
        self.stop_loss_pct = tournament.stop_loss_pct if tournament else 0.015
        self.take_profit_pct = tournament.take_profit_pct if tournament else 0.06
        self.last_trade_date = None
        self.daily_trade_made = False

    def _reset_if_new_day(self) -> None:
        today = datetime.now(timezone.utc).date()
        if today != self.last_trade_date:
            self.daily_trade_made = False
            self.last_trade_date = today

    def mark_trade_executed(self) -> None:
        self._reset_if_new_day()
        self.daily_trade_made = True

    def sync_from_portfolio(self, trades_today: int) -> None:
        self._reset_if_new_day()
        if trades_today > 0:
            self.daily_trade_made = True

    async def ensure_daily_trade(
        self,
        portfolio: dict,
        scan_fn: ScanFn,
        execute_fn: ExecuteFn,
        find_safest_token_fn: SafestTokenFn,
    ) -> Optional[dict]:
        if not self.enabled:
            return None

        self.sync_from_portfolio(portfolio.get("trades_today", 0))
        now = datetime.now(timezone.utc)

        if self.daily_trade_made or portfolio.get("trades_today", 0) > 0:
            return None
        if now.hour < self.enforce_hour:
            return None

        signals = await scan_fn()
        if signals:
            strongest = max(signals, key=lambda s: s.confidence)
            strongest.reason = f"Daily qualification (best signal) | {strongest.reason}"
            trade = await execute_fn(strongest)
            if trade:
                self.daily_trade_made = True
                logger.info("Daily qualification trade (signal): %s", strongest.token)
            return trade

        safest = await find_safest_token_fn()
        if not safest:
            logger.warning("Trade enforcer: no eligible token for qualification")
            return None

        qual_signal = TradeSignal(
            strategy="QUALIFICATION",
            action="BUY",
            token=safest,
            token_to="USDT",
            confidence=0.5,
            expected_return=0.005,
            risk=0.1,
            position_size_pct=self.qualification_size,
            reason=f"Qualification trade: lowest volatility ({safest}) at {self.qualification_size * 100:.1f}%",
            stop_loss_pct=self.stop_loss_pct,
            take_profit_pct=self.take_profit_pct,
        )
        trade = await execute_fn(qual_signal)
        if trade:
            self.daily_trade_made = True
            logger.info("Qualification trade: %s at %.1f%%", safest, self.qualification_size * 100)
        return trade


TradeEnforcer = SmartTradeEnforcer

"""Strategy 2: Smart Money Shadow — copy profitable whale trades."""

import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from strategies.signal_generation import TradeSignal
from validation.token_validator import TokenValidator

logger = logging.getLogger(__name__)


@dataclass
class WhaleWallet:
    address: str
    category: str
    win_rate: float
    avg_return: float
    portfolio_usd: float
    trade_count: int
    last_active: datetime
    paused_until: Optional[datetime] = None


# Simulated whale watchlist for paper/competition mode
DEFAULT_WHALES = [
    WhaleWallet(
        address="0xWhale1" + "a" * 34,
        category="Smart DEX Trader",
        win_rate=0.72,
        avg_return=0.10,
        portfolio_usd=250_000,
        trade_count=150,
        last_active=datetime.now(timezone.utc),
    ),
    WhaleWallet(
        address="0xWhale2" + "b" * 34,
        category="Early Token Buyer",
        win_rate=0.68,
        avg_return=0.12,
        portfolio_usd=180_000,
        trade_count=120,
        last_active=datetime.now(timezone.utc),
    ),
    WhaleWallet(
        address="0xWhale3" + "c" * 34,
        category="Institutional Proxy",
        win_rate=0.66,
        avg_return=0.09,
        portfolio_usd=500_000,
        trade_count=200,
        last_active=datetime.now(timezone.utc),
    ),
]


class WhaleShadow:
    """Secondary strategy — shadow smart money on BSC (requires on-chain indexer)."""

    SIMULATED = True  # Paper mode uses random signals; disable in orchestrator until live

    ALLOCATION = 0.30
    STRATEGY_NAME = "WHALE"
    MIN_CONFIDENCE = 0.75
    MAX_WHALE_ALLOCATION = 0.10

    def __init__(self, validator: TokenValidator):
        self.validator = validator
        self.whales: list[WhaleWallet] = DEFAULT_WHALES.copy()
        self._recent_tokens: dict[str, datetime] = {}
        self._copied_trades: list[dict] = []

    def _whale_meets_criteria(self, whale: WhaleWallet) -> bool:
        if whale.paused_until and datetime.now(timezone.utc) < whale.paused_until:
            return False
        if whale.trade_count < 100:
            return False
        if whale.win_rate < 0.65:
            return False
        if whale.avg_return < 0.08:
            return False
        if whale.portfolio_usd < 50_000:
            return False
        if (datetime.now(timezone.utc) - whale.last_active).days > 30:
            return False
        return True

    def _calculate_confidence(self, whale: WhaleWallet, trade_size_usd: float) -> float:
        recency = max(0.5, 1 - (datetime.now(timezone.utc) - whale.last_active).days / 30)
        size_factor = min(1.0, trade_size_usd / 10_000)
        return whale.win_rate * recency * size_factor

    def _check_correlation(self, token: str) -> bool:
        """Return True if we should skip (too many whales buying same token)."""
        recent = self._recent_tokens.get(token)
        if recent and (datetime.now(timezone.utc) - recent).total_seconds() < 3600:
            return True
        return False

    async def detect_whale_signals(self) -> list[TradeSignal]:
        """Scan whale activity. In production, monitors on-chain via BSC indexer."""
        signals: list[TradeSignal] = []

        for whale in self.whales:
            if not self._whale_meets_criteria(whale):
                continue

            # Simulate whale swap detection (production: BSC event listener)
            if random.random() > 0.3:
                continue

            token = random.choice(["CAKE", "ETH", "DOGE", "SHIB", "LINK", "FLOKI"])
            trade_size = random.uniform(5_000, 50_000)
            action = "BUY" if random.random() > 0.3 else "SELL"

            if not self.validator.is_eligible(token):
                logger.info("Whale trade rejected: %s not eligible", token)
                continue

            if self._check_correlation(token):
                logger.info("Whale trade skipped: correlation on %s", token)
                continue

            confidence = self._calculate_confidence(whale, trade_size)
            if confidence < self.MIN_CONFIDENCE:
                continue

            entry_price = random.uniform(1, 100)
            signals.append(
                TradeSignal(
                    strategy=self.STRATEGY_NAME,
                    action=action,
                    token=token,
                    token_to="USDT" if action == "SELL" else "BNB",
                    confidence=confidence,
                    expected_return=0.15,
                    risk=1.2,
                    position_size_pct=min(
                        self.ALLOCATION * confidence * 0.5,
                        self.MAX_WHALE_ALLOCATION,
                    ),
                    reason=f"Whale {whale.address[:10]}... {action} ${trade_size:.0f} "
                    f"(win_rate={whale.win_rate:.0%})",
                    stop_loss_pct=0.05,
                    take_profit_pct=0.15,
                )
            )
            self._recent_tokens[token] = datetime.now(timezone.utc)

        return signals

    def record_whale_trade_result(self, whale_address: str, pnl_pct: float) -> None:
        for whale in self.whales:
            if whale.address == whale_address and pnl_pct < -0.05:
                whale.paused_until = datetime.now(timezone.utc) + timedelta(hours=24)
                logger.warning("Whale %s paused for 24h after >5%% loss", whale_address[:10])

    def get_whale_stats(self) -> list[dict]:
        return [
            {
                "address": w.address[:12] + "...",
                "category": w.category,
                "win_rate": w.win_rate,
                "portfolio_usd": w.portfolio_usd,
                "active": self._whale_meets_criteria(w),
            }
            for w in self.whales
        ]

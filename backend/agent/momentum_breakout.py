"""Strategy 3: Momentum Breakout — directional momentum on eligible tokens."""

import logging
from typing import Optional

from data.cmchub_client import CMCHubClient
from strategies.signal_generation import TradeSignal
from strategies.technical import atr
from validation.token_validator import TokenValidator

logger = logging.getLogger(__name__)

# High-liquidity tokens to scan; filtered through eligible whitelist at runtime
SCAN_CANDIDATES = [
    "CAKE", "ETH", "DOGE", "SHIB", "LINK", "AVAX", "ADA", "DOT", "UNI",
    "FLOKI", "BONK", "XRP", "LTC", "ATOM", "INJ", "AAVE", "FET",
]


class MomentumBreakout:
    """Tertiary strategy — buy high-momentum eligible tokens, ride trend, sell higher."""

    STRATEGY_NAME = "MOMENTUM"
    POSITION_SIZE_PCT = 0.15
    STOP_LOSS_PCT = 0.03
    PERIOD_HIGH = 20
    VOLUME_MULTIPLIER = 1.5
    MAX_HOLD_HOURS = 48
    TRAILING_ATR_MULT = 2.0

    def __init__(self, cmc: CMCHubClient, validator: TokenValidator):
        self.cmc = cmc
        self.validator = validator

    def _eligible_scan_tokens(self) -> list[str]:
        return [t for t in SCAN_CANDIDATES if self.validator.is_eligible(t)]

    async def scan_breakouts(self) -> list[TradeSignal]:
        signals: list[TradeSignal] = []
        tokens = self._eligible_scan_tokens()

        for token in tokens:
            signal = await self._check_breakout(token)
            if signal:
                signals.append(signal)

        if not signals:
            logger.debug("No momentum breakouts detected among %d eligible tokens", len(tokens))

        return signals

    async def _check_breakout(self, token: str) -> Optional[TradeSignal]:
        if not self.validator.is_eligible(token):
            logger.info("Momentum signal rejected: %s not eligible", token)
            return None

        ohlcv = await self.cmc.get_ohlcv(token, interval="1h", limit=50)
        high = ohlcv["high"]
        low = ohlcv["low"]
        close = ohlcv["close"]
        volume = ohlcv["volume"]

        if len(close) < self.PERIOD_HIGH + 1:
            return None

        period_high = max(high[-(self.PERIOD_HIGH + 1) : -1])
        current_price = close[-1]
        avg_volume = sum(volume[-20:]) / min(20, len(volume))

        if current_price <= period_high:
            return None
        if volume[-1] < self.VOLUME_MULTIPLIER * avg_volume:
            return None

        atr_vals = atr(high, low, close, 14)
        atr_trail = atr_vals[-1] * self.TRAILING_ATR_MULT if atr_vals else current_price * 0.03
        breakout_pct = (current_price - period_high) / period_high if period_high else 0

        return TradeSignal(
            strategy=self.STRATEGY_NAME,
            action="BUY",
            token=token,
            token_to="USDT",
            confidence=min(0.95, 0.65 + breakout_pct * 5),
            expected_return=0.12,
            risk=1.0,
            position_size_pct=self.POSITION_SIZE_PCT,
            reason=(
                f"Breakout above {self.PERIOD_HIGH}p high ${period_high:.4f} "
                f"with volume {volume[-1]/avg_volume:.1f}x avg"
            ),
            stop_loss_pct=self.STOP_LOSS_PCT,
            take_profit_pct=0.0,  # exit via trailing stop or 48h max hold
        )

    def get_stats(self) -> dict:
        eligible = self._eligible_scan_tokens()
        return {
            "strategy": self.STRATEGY_NAME,
            "scan_tokens": len(eligible),
            "position_size_pct": self.POSITION_SIZE_PCT * 100,
            "stop_loss_pct": self.STOP_LOSS_PCT * 100,
            "max_hold_hours": self.MAX_HOLD_HOURS,
            "eligible_tokens_scanned": eligible,
        }

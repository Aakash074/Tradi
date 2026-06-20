"""Pre-trade validation checklist — all checks must pass."""

import logging
from typing import Optional

from strategies.technical import atr, sma

logger = logging.getLogger(__name__)


def _recent_swing_low(ohlcv: dict, periods: int = 10) -> float:
    lows = ohlcv.get("low", ohlcv.get("close", []))
    window = lows[-periods:] if len(lows) >= periods else lows
    return min(window) if window else 0.0


def _has_high_impact_news(token: str, next_hours: int = 2) -> bool:
    """Stub — no news feed in paper mode."""
    return False


class PreTradeChecklist:
    """Real trader checklist — ALL must pass."""

    def __init__(self, account_size: float = 10000):
        self.account_size = account_size
        self.max_risk_pct = 0.02

    def get_bid_ask_spread(self, token: str, ohlcv: Optional[dict] = None) -> float:
        """Estimate spread from recent volatility when order book unavailable."""
        if not ohlcv:
            return 0.003
        close = ohlcv.get("close", [])
        if len(close) < 5:
            return 0.005
        recent_range = max(close[-5:]) - min(close[-5:])
        mid = (max(close[-5:]) + min(close[-5:])) / 2
        return min(0.02, (recent_range / mid) * 0.1) if mid else 0.01

    def validate(
        self,
        token: str,
        entry_price: float,
        stop_price: float,
        target_price: float,
        ohlcv: Optional[dict] = None,
    ) -> tuple[bool, list[str], float]:
        failed: list[str] = []
        ohlcv = ohlcv or {}

        spread = self.get_bid_ask_spread(token, ohlcv)
        if spread > 0.005:
            failed.append(f"WIDE_SPREAD: {spread:.3f}")

        volume = ohlcv.get("volume", [])
        recent = volume[-24:] if len(volume) >= 24 else volume
        vol_mean = sum(recent) / len(recent) if recent else 0.0
        vol_sma = sma(volume, 20)
        vol_avg = vol_sma[-1] if vol_sma else (sum(volume) / len(volume) if volume else 0)
        if vol_avg > 0 and vol_mean < vol_avg * 0.8:
            failed.append("LOW_VOLUME")

        risk = entry_price - stop_price
        reward = target_price - entry_price
        if risk <= 0 or reward <= 0:
            failed.append("INVALID_RR")
        elif reward / risk < 2.0:
            failed.append(f"POOR_RR: {reward / risk:.2f}")

        risk_amount = self.account_size * self.max_risk_pct
        if risk > 0:
            position_size = risk_amount / risk
            position_size = min(position_size, self.account_size * 0.05)
        else:
            position_size = 0.0
            failed.append("ZERO_RISK")

        swing_low = _recent_swing_low(ohlcv, 10)
        if swing_low > 0 and stop_price > swing_low * 1.02:
            failed.append("STOP_NOT_TECHNICAL")

        if _has_high_impact_news(token):
            failed.append("NEWS_EVENT")

        close = ohlcv.get("close", [])
        high = ohlcv.get("high", close)
        low = ohlcv.get("low", close)
        atr_vals = atr(high, low, close, 14) if len(close) >= 15 else []
        atr_val = atr_vals[-1] if atr_vals else entry_price * 0.02
        if atr_val > 0 and spread * entry_price > atr_val * 0.3:
            failed.append("EXPENSIVE_SPREAD")

        passed = len(failed) == 0
        return passed, failed, position_size

    def log_check(
        self,
        token: str,
        entry: float,
        stop: float,
        target: float,
        ohlcv: Optional[dict] = None,
    ) -> tuple[bool, float]:
        passed, failed, size = self.validate(token, entry, stop, target, ohlcv)
        logger.info("PRE_TRADE_CHECK: %s passed=%s", token, passed)
        if failed:
            logger.info("CHECKLIST failed: %s", ", ".join(failed))
        else:
            logger.info("CHECKLIST passed position_size=$%.2f", size)
        return passed, size

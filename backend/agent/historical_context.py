"""Five-hour historical context analysis before trade entry."""

import logging
from typing import Union

import numpy as np

logger = logging.getLogger(__name__)


class HistoricalContextAnalyzer:
    """Analyze last ~5 hours (20 x 15m bars) before taking any trade."""

    def analyze(self, token: str, ohlcv: dict) -> tuple[bool, str, float]:
        """
        Returns: (is_valid, reason, confidence_score)
        TEMPORARY DISABLE — neutral pass for paper testing.
        """
        return True, "PASSED", 0.6

        close = np.array(ohlcv.get("close", []), dtype=float)
        low = np.array(ohlcv.get("low", close), dtype=float)
        volume = np.array(ohlcv.get("volume", []), dtype=float)

        if len(close) < 20:
            return False, "INSUFFICIENT_DATA", 0.0

        df_5h = close[-20:]
        vol_5h = volume[-20:] if len(volume) >= 20 else volume
        low_5h = low[-20:] if len(low) >= 20 else low

        trend_strength = abs(df_5h[-1] - df_5h[0]) / df_5h[0] if df_5h[0] else 0.0

        direction_changes = 0
        for i in range(2, len(df_5h)):
            sign_now = np.sign(df_5h[i] - df_5h[i - 1])
            sign_prev = np.sign(df_5h[i - 1] - df_5h[i - 2])
            if sign_now != 0 and sign_prev != 0 and sign_now != sign_prev:
                direction_changes += 1

        if direction_changes > 8:
            logger.info("%s: Rejected - CHOPPY_5H (%d direction changes)", token, direction_changes)
            return False, "CHOPPY_5H", 0.2

        avg_volume = float(np.mean(vol_5h)) if len(vol_5h) else 0.0
        recent_volume = float(np.mean(vol_5h[-5:])) if len(vol_5h) >= 5 else avg_volume
        if avg_volume > 0 and recent_volume < avg_volume * 0.8:
            logger.info("%s: Rejected - DECLINING_VOLUME", token)
            return False, "DECLINING_VOLUME", 0.3

        pct_changes = np.diff(df_5h) / df_5h[:-1]
        volatility = float(np.std(pct_changes)) if len(pct_changes) > 1 else 0.0
        if volatility > 0.05:
            logger.info("%s: Rejected - HIGH_VOLATILITY (%.2f%%)", token, volatility * 100)
            return False, "HIGH_VOLATILITY", 0.3

        recent_low = float(np.min(low_5h[-5:]))
        prior_low = float(np.min(low_5h[:-5])) if len(low_5h) > 5 else recent_low
        structure_score = 0.9 if recent_low > prior_low * 1.02 else 0.5

        confidence = min(1.0, structure_score + (trend_strength * 5))
        return True, "STRONG_5H_CONTEXT", confidence

    def get_context_summary(self, token: str, ohlcv: dict) -> dict:
        valid, reason, conf = self.analyze(token, ohlcv)
        close = ohlcv.get("close", [])
        if len(close) < 2:
            return {"valid": valid, "reason": reason, "confidence": conf}
        pct = np.diff(np.array(close[-20:], dtype=float)) / np.array(close[-20:-1], dtype=float)
        vol_pct = float(np.std(pct)) * 100 if len(pct) > 1 else 0.0
        return {
            "valid": valid,
            "reason": reason,
            "confidence": conf,
            "trend": "UP" if close[-1] > close[-min(20, len(close))] else "DOWN",
            "volatility": vol_pct,
        }

"""Liquidity sweep detection — stop-hunt below EMA20 + reversal."""

import logging
from typing import Optional

from strategies.technical import ema

logger = logging.getLogger(__name__)


class LiquiditySweepDetector:
    """Detect stop-hunts below EMA20 with volume spike and recovery."""

    def detect(self, token: str, ohlcv: dict) -> tuple[bool, Optional[dict]]:
        close = ohlcv.get("close", [])
        low = ohlcv.get("low", close)
        volume = ohlcv.get("volume", [])

        if len(close) < 25 or len(volume) < 20:
            return False, None

        ema20_vals = ema(close, 20)
        if not ema20_vals:
            return False, None

        current_price = close[-1]
        ema20_now = ema20_vals[-1]
        vol_now = volume[-1]
        avg_volume = sum(volume[-20:]) / 20

        recent_lows = low[-5:]
        recent_emas = ema20_vals[-5:]
        sweep_low = min(recent_lows)
        swept = any(l < e * 0.995 for l, e in zip(recent_lows, recent_emas))

        volume_spike = vol_now > avg_volume * 1.5 if avg_volume > 0 else False
        recovery = current_price > ema20_now * 0.998

        if swept and volume_spike and recovery:
            data = {
                "token": token,
                "sweep_price": sweep_low,
                "ema20": ema20_now,
                "current_price": current_price,
                "volume_ratio": vol_now / avg_volume if avg_volume else 1.0,
            }
            logger.info(
                "SWEEP: %s sweep_price=%.6f ema20=%.6f vol_ratio=%.2f",
                token,
                sweep_low,
                ema20_now,
                data["volume_ratio"],
            )
            return True, data

        return False, None

    def get_sweep_quality(self, sweep_data: Optional[dict]) -> float:
        if not sweep_data:
            return 0.0
        vol_ratio = sweep_data.get("volume_ratio", 1.0)
        price = sweep_data.get("current_price", 0)
        ema20 = sweep_data.get("ema20", price)
        recovery_pct = (price - sweep_data.get("sweep_price", price)) / price if price else 0
        ema_recovery = 1.0 if price > ema20 else 0.5
        vol_score = min(1.0, (vol_ratio - 1.0) / 1.0)
        quality = 0.4 * ema_recovery + 0.3 * vol_score + 0.3 * min(1.0, recovery_pct * 50)
        return min(1.0, max(0.0, quality))

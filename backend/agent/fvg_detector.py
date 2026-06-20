"""Fair Value Gap (FVG) detection — imbalance zones."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class FVGDetector:
    """Detect unmitigated FVGs where price often returns."""

    def find_fvgs(self, ohlcv: dict, lookback: int = 20) -> list[dict]:
        high = ohlcv.get("high", [])
        low = ohlcv.get("low", [])
        close = ohlcv.get("close", [])
        n = min(len(close), lookback + 2)
        if n < 3:
            return []

        close = close[-n:]
        high = high[-n:]
        low = low[-n:]
        fvgs: list[dict] = []

        for i in range(2, len(close)):
            if low[i] > high[i - 2]:
                fvgs.append({
                    "type": "BULLISH",
                    "top": low[i],
                    "bottom": high[i - 2],
                    "index": i,
                    "mitigated": False,
                })
            elif high[i] < low[i - 2]:
                fvgs.append({
                    "type": "BEARISH",
                    "top": low[i - 2],
                    "bottom": high[i],
                    "index": i,
                    "mitigated": False,
                })

        current_price = close[-1]
        active: list[dict] = []
        for fvg in fvgs:
            if fvg["type"] == "BULLISH":
                if current_price > fvg["bottom"]:
                    dist = (current_price - fvg["bottom"]) / fvg["bottom"]
                    if dist < 0.02:
                        fvg["distance"] = dist
                        active.append(fvg)
            elif current_price < fvg["top"]:
                dist = (fvg["top"] - current_price) / current_price
                if dist < 0.02:
                    fvg["distance"] = dist
                    active.append(fvg)

        return active

    def is_near_fvg(
        self, ohlcv: dict, current_price: float, threshold: float = 0.01
    ) -> tuple[bool, Optional[dict]]:
        fvgs = self.find_fvgs(ohlcv, lookback=20)
        for fvg in fvgs:
            if fvg["type"] == "BULLISH":
                if abs(current_price - fvg["bottom"]) / current_price < threshold:
                    logger.info("FVG: near BULLISH FVG bottom=%.6f", fvg["bottom"])
                    return True, fvg
            else:
                if abs(current_price - fvg["top"]) / current_price < threshold:
                    logger.info("FVG: near BEARISH FVG top=%.6f", fvg["top"])
                    return True, fvg
        return False, None

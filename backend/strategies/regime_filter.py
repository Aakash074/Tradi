"""Layer 1: Regime filter — DEFENSIVE / NORMAL / AGGRESSIVE."""

from enum import Enum
from typing import Optional

from data.cmchub_client import CMCHubClient


class RegimeMode(str, Enum):
    DEFENSIVE = "DEFENSIVE"
    NORMAL = "NORMAL"
    AGGRESSIVE = "AGGRESSIVE"


async def regime_filter(cmc: CMCHubClient, symbol: str = "CAKE") -> tuple[RegimeMode, dict]:
    """
    Binary-ish regime from volatility ratio + Fear & Greed.
    DEFENSIVE: high vol or extreme fear — no new positions.
    AGGRESSIVE: low vol + greed — full Kelly sizing.
    NORMAL: half Kelly.
    """
    vol_24h = await cmc.get_24h_volatility(symbol)
    vol_30d = await cmc.get_30d_volatility(symbol)
    fng_data = await cmc.get_fear_greed_index()
    fng = fng_data.get("value", 50)

    vol_ratio = vol_24h / vol_30d if vol_30d > 0 else 1.0
    metrics = {
        "vol_24h": vol_24h,
        "vol_30d": vol_30d,
        "vol_ratio": vol_ratio,
        "fear_greed": fng,
        "fear_greed_classification": fng_data.get("classification", "Neutral"),
        "fear_greed_source": fng_data.get("source", "unknown"),
    }

    if vol_ratio > 1.5 or fng < 20:
        mode = RegimeMode.DEFENSIVE
    elif vol_ratio < 0.7 and fng > 50:
        mode = RegimeMode.AGGRESSIVE
    else:
        mode = RegimeMode.NORMAL

    metrics["regime_mode"] = mode.value
    return mode, metrics


def kelly_multiplier(regime: RegimeMode) -> float:
    if regime == RegimeMode.DEFENSIVE:
        return 0.0
    if regime == RegimeMode.AGGRESSIVE:
        return 1.0
    return 0.5

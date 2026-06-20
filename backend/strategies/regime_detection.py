"""Market regime detection for Tradi Market State Adapter strategy."""

from enum import Enum

from strategies.technical import adx, atr


class MarketRegime(str, Enum):
    TRENDING = "TRENDING"
    RANGING = "RANGING"
    VOLATILE = "VOLATILE"
    ACCUMULATION = "ACCUMULATION"


REGIME_STRATEGY_MAP: dict[MarketRegime, str] = {
    MarketRegime.TRENDING: "Momentum Strategy",
    MarketRegime.RANGING: "Mean Reversion Strategy",
    MarketRegime.VOLATILE: "Breakout Strategy",
    MarketRegime.ACCUMULATION: "DCA Strategy",
}


def get_regime_strategy_label(regime: MarketRegime) -> str:
    return REGIME_STRATEGY_MAP.get(regime, "DCA Strategy")


def detect_regime(
    high: list[float],
    low: list[float],
    close: list[float],
    adx_period: int = 14,
    atr_period: int = 14,
) -> tuple[MarketRegime, dict]:
    """Classify market regime using ADX and ATR."""
    adx_vals = adx(high, low, close, adx_period)
    atr_vals = atr(high, low, close, atr_period)

    if not adx_vals or not atr_vals:
        return MarketRegime.ACCUMULATION, {"reason": "Insufficient data"}

    current_adx = adx_vals[-1]
    current_atr = atr_vals[-1]
    avg_atr = sum(atr_vals[-20:]) / min(20, len(atr_vals))
    atr_ratio = current_atr / avg_atr if avg_atr else 1.0

    metrics = {
        "adx": current_adx,
        "atr": current_atr,
        "avg_atr": avg_atr,
        "atr_ratio": atr_ratio,
        "active_strategy": "",
    }

    if current_adx > 25 and current_atr > 1.5 * avg_atr:
        regime = MarketRegime.TRENDING
    elif current_adx < 20:
        regime = MarketRegime.RANGING
    elif current_atr > 2 * avg_atr:
        regime = MarketRegime.VOLATILE
    else:
        regime = MarketRegime.ACCUMULATION

    metrics["active_strategy"] = get_regime_strategy_label(regime)
    return regime, metrics

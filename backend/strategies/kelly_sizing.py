"""Position sizing — volatility-adjusted deployment."""

from strategies.regime_filter import RegimeMode

BASE_SIZE_AGGRESSIVE = 0.04
BASE_SIZE_DYNAMIC = 0.04
MAX_POSITION_PCT = 0.05


def position_size(signal_strength: float, current_drawdown: float) -> float:
    """Legacy fixed sizing."""
    if current_drawdown > 0.10:
        return 0.01
    if signal_strength > 0.8:
        return 0.04
    return 0.03


def aggressive_sizing(
    signal_strength: float,
    current_drawdown: float = 0.0,
    atr_pct: float = 0.02,
) -> float:
    """Tournament aggressive sizing — 4% base, max 5%."""
    if current_drawdown > 0.10:
        return 0.01
    signal_factor = 0.5 + (signal_strength * 0.7)
    vol_factor = min(0.03 / max(atr_pct, 0.01), 1.5)
    size = BASE_SIZE_AGGRESSIVE * signal_factor * vol_factor
    return min(size, MAX_POSITION_PCT)


def dynamic_sizing(
    atr_pct: float,
    signal_strength: float,
    regime_mode: RegimeMode = RegimeMode.NORMAL,
    current_drawdown: float = 0.0,
    sizing_mode: str = "dynamic",
) -> float:
    """
    Scale into volatility inversely, scale up with signal strength.
    sizing_mode: dynamic | aggressive (tournament)
    """
    if regime_mode == RegimeMode.DEFENSIVE:
        return 0.0
    if current_drawdown > 0.10:
        return 0.01

    if sizing_mode == "aggressive":
        return aggressive_sizing(signal_strength, current_drawdown, atr_pct)

    base_size = BASE_SIZE_DYNAMIC
    vol_factor = 0.03 / max(atr_pct, 0.01)
    vol_factor = min(vol_factor, 2.0)
    signal_factor = 0.5 + (signal_strength * 0.7)

    size = base_size * vol_factor * signal_factor

    if regime_mode == RegimeMode.AGGRESSIVE:
        size *= 1.5

    return min(size, MAX_POSITION_PCT)

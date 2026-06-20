"""Asymmetric exit levels — 1:3 risk/reward with trailing stop."""

from dataclasses import dataclass
from typing import Optional


STOP_LOSS_PCT = 0.015       # 1.5% max loss (production default)
TAKE_PROFIT_PCT = 0.045     # 4.5% gain — 1:3 R/R with 1.5% stop
TRAILING_ACTIVATION_PCT = 0.03  # Activate at +3%
TRAILING_DISTANCE_PCT = 0.01    # Trail 1% below high


@dataclass
class ExitLevels:
    stop_loss: float
    take_profit: float
    trailing_activation: float
    trailing_distance: float
    risk_pct: float
    reward_pct: float


def set_exit_levels(
    entry_price: float,
    atr: Optional[float] = None,
    stop_loss_pct: float = STOP_LOSS_PCT,
    take_profit_pct: float = TAKE_PROFIT_PCT,
    trailing_activation_pct: float = TRAILING_ACTIVATION_PCT,
) -> ExitLevels:
    """
    Asymmetric exits: 1.5% stop, 4.5% target (1:3 R/R).
    Tournament overrides via config (e.g. 1.5:6.0). Trailing at +3%, 1% below high.
    """
    stop = entry_price * (1 - stop_loss_pct)
    target = entry_price * (1 + take_profit_pct)

    # Optional ATR tightening — never widen beyond configured stop
    if atr and atr > 0:
        atr_stop = entry_price - 2 * atr
        stop = max(stop, atr_stop)

    return ExitLevels(
        stop_loss=stop,
        take_profit=target,
        trailing_activation=entry_price * (1 + trailing_activation_pct),
        trailing_distance=TRAILING_DISTANCE_PCT,
        risk_pct=stop_loss_pct,
        reward_pct=take_profit_pct,
    )


def apply_trailing_stop(
    current_price: float,
    entry_price: float,
    stop_loss: float,
    trailing_activation: float,
    trailing_distance: float,
) -> float:
    """Update stop if price passed trailing activation threshold."""
    if current_price >= trailing_activation:
        trail_stop = current_price * (1 - trailing_distance)
        if trail_stop > stop_loss:
            return trail_stop
    return stop_loss

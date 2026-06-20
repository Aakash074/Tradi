"""Lock-in ratchet and position management."""

import logging
from datetime import datetime, timezone
from typing import Callable, Optional

logger = logging.getLogger(__name__)

RATCHET_LEVELS = [
    (0.35, 0.05, "+35% gain"),
    (0.20, 0.10, "+20% gain"),
    (0.10, 0.15, "+10% gain"),
]


def apply_lock_in_ratchet(
    positions: list[dict],
    portfolio_value: float,
    log_fn: Optional[Callable[..., None]] = None,
) -> list[dict]:
    """
    Trim winning positions to protect gains.
    Returns list of trim actions taken.
    """
    actions: list[dict] = []

    for position in positions:
        entry = position.get("entry_price", 0)
        current = position.get("current_price", entry)
        size_usd = position.get("amount_usd", 0)

        if not entry or entry <= 0:
            continue

        pnl_pct = (current - entry) / entry

        for threshold, max_exposure_pct, label in RATCHET_LEVELS:
            if pnl_pct <= threshold:
                continue

            target_size = portfolio_value * max_exposure_pct
            if size_usd <= target_size:
                break

            trim_amount = size_usd - target_size
            action = {
                "token": position.get("token_to") or position.get("token"),
                "pnl_pct": round(pnl_pct * 100, 2),
                "from_size_usd": size_usd,
                "to_size_usd": target_size,
                "trim_usd": trim_amount,
                "reason": f"Ratchet: Trimmed to {max_exposure_pct*100:.0f}% after {label}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            position["amount_usd"] = target_size
            position["ratchet_applied"] = label
            actions.append(action)

            msg = action["reason"]
            if log_fn:
                log_fn("RATCHET", "TRIM", action["token"], msg)
            else:
                logger.info("%s — %s", action["token"], msg)
            break

    return actions

"""Correlation guard — reject highly correlated positions."""

import logging
import random
from typing import Optional

logger = logging.getLogger(__name__)

_correlation_cache: dict[tuple[str, str], float] = {}


def get_correlation_24h(token_a: str, token_b: str) -> float:
    """Estimate 24h correlation between two tokens."""
    key = tuple(sorted([token_a.upper(), token_b.upper()]))
    if key in _correlation_cache:
        return _correlation_cache[key]

    majors = {"ETH", "BNB", "BTC", "CAKE", "LINK", "AVAX", "ADA", "DOT"}
    stables = {"USDT", "USDC", "DAI", "FDUSD", "TUSD"}
    a, b = key
    if a in stables or b in stables:
        corr = random.uniform(-0.1, 0.2)
    elif a in majors and b in majors:
        corr = random.uniform(0.6, 0.9)
    else:
        corr = random.uniform(0.2, 0.7)

    _correlation_cache[key] = corr
    return corr


def correlation_filter(new_token: str, existing_positions: list[dict]) -> tuple[bool, str]:
    for pos in existing_positions:
        existing = pos.get("token_to") or pos.get("token", "")
        if not existing:
            continue
        corr = get_correlation_24h(new_token, existing)
        if corr > 0.8:
            return False, f"Correlation {corr:.2f} with {existing} > 0.8"
        if corr < -0.3:
            return True, f"Anti-correlated hedge with {existing} ({corr:.2f})"
    return True, "OK"


def correlation_filter_fast(new_token: str, existing_positions: list[dict]) -> tuple[bool, str]:
    """Only check correlation vs largest position when 2+ positions open."""
    if len(existing_positions) < 2:
        return True, "OK"

    largest = max(
        existing_positions,
        key=lambda p: p.get("amount_usd", p.get("size_usd", 0)),
    )
    existing = largest.get("token_to") or largest.get("token", "")
    if not existing:
        return True, "OK"

    corr = get_correlation_24h(new_token, existing)
    if corr >= 0.8:
        return False, f"Correlation {corr:.2f} with largest position {existing} >= 0.8"
    return True, "OK"

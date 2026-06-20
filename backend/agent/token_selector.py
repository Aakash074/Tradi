"""Token universe selection — top momentum filter for tournament mode."""

import logging
import time
from typing import Optional

from data.cmchub_client import CMCHubClient
from validation.token_validator import TokenValidator

logger = logging.getLogger(__name__)

# Liquid candidates scanned for momentum ranking (subset for responsiveness)
MOMENTUM_CANDIDATES = [
    "CAKE", "ETH", "DOGE", "SHIB", "LINK", "BNB", "ADA", "AVAX", "DOT", "UNI",
    "AAVE", "ATOM", "FIL", "INJ", "LTC", "BCH", "TON", "XRP", "TRX", "SOL",
]


async def compute_24h_momentum(cmc: CMCHubClient, token: str) -> Optional[float]:
    """Return 24h price change as a fraction (e.g. 0.05 = +5%)."""
    try:
        ohlcv = await cmc.get_ohlcv(token, interval="1h", limit=24)
        close = ohlcv.get("close", [])
        if len(close) < 2:
            return None
        return (close[-1] - close[0]) / close[0] if close[0] else None
    except Exception as e:
        logger.debug("Momentum calc failed for %s: %s", token, e)
        return None


async def get_top_momentum_tokens(
    cmc: CMCHubClient,
    validator: TokenValidator,
    limit: int = 20,
    candidate_tokens: Optional[list[str]] = None,
) -> list[str]:
    """Rank eligible tokens by 24h momentum, return top N."""
    if candidate_tokens is None:
        candidate_tokens = [t for t in MOMENTUM_CANDIDATES if validator.is_eligible(t)]
        if len(candidate_tokens) < limit:
            candidate_tokens = validator.eligible_tokens[:60]
    tokens = candidate_tokens
    ranked: list[tuple[str, float]] = []

    for token in tokens:
        if not validator.is_eligible(token):
            continue
        momentum = await compute_24h_momentum(cmc, token)
        if momentum is not None:
            ranked.append((token, momentum))

    ranked.sort(key=lambda x: x[1], reverse=True)
    top = [t for t, _ in ranked[:limit]]
    logger.info("Top %d momentum tokens: %s", limit, ", ".join(top[:5]) + ("..." if len(top) > 5 else ""))
    return top


class TokenSelector:
    """Maintains tournament scan universe (top N by momentum)."""

    def __init__(
        self,
        cmc: CMCHubClient,
        validator: TokenValidator,
        top_n: int = 20,
        mode: str = "top_20_momentum",
        refresh_ttl: int = 900,
    ):
        self.cmc = cmc
        self.validator = validator
        self.top_n = top_n
        self.mode = mode
        self.refresh_ttl = refresh_ttl
        self._universe: list[str] = []
        self._momentum_rank: dict[str, float] = {}
        self._last_refresh: float = 0.0

    async def refresh(self, force: bool = False) -> list[str]:
        if (
            not force
            and self._universe
            and (time.monotonic() - self._last_refresh) < self.refresh_ttl
        ):
            return self._universe

        if self.mode == "top_20_momentum":
            # Testing: top 50 instead of 20 for broader signal coverage
            scan_limit = 50
            tokens = await get_top_momentum_tokens(self.cmc, self.validator, scan_limit)
            self._universe = tokens
            self._momentum_rank = {}
            for token in tokens:
                mom = await compute_24h_momentum(self.cmc, token)
                if mom is not None:
                    self._momentum_rank[token] = mom
        else:
            self._universe = [
                t for t in self.validator.eligible_tokens if self.validator.is_eligible(t)
            ][: self.top_n]
        self._last_refresh = time.monotonic()
        return self._universe

    @property
    def universe(self) -> list[str]:
        return self._universe

    def is_in_universe(self, token: str) -> bool:
        if not self._universe:
            return True
        return token in self._universe

    def get_status(self) -> dict:
        return {
            "mode": self.mode,
            "top_n": self.top_n,
            "universe": self._universe,
            "momentum_rank": {
                k: round(v * 100, 2) for k, v in sorted(
                    self._momentum_rank.items(), key=lambda x: x[1], reverse=True
                )
            },
        }

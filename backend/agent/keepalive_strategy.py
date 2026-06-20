"""Always-on keepalive strategy — ensures minimum 1 trade per UTC day."""

import logging
from datetime import datetime, timezone
from typing import Optional

from data.cmchub_client import CMCHubClient
from strategies.signal_generation import TradeSignal
from validation.token_validator import TokenValidator

logger = logging.getLogger(__name__)

VOLUME_CANDIDATES = [
    "CAKE", "ETH", "DOGE", "SHIB", "LINK", "BNB", "ADA",
    "AVAX", "DOT", "UNI", "AAVE", "ATOM", "FIL", "INJ",
    "LTC", "BCH", "TON", "DAI", "USDT", "USDC",
]


class KeepaliveStrategy:
    """Ensures 1 trade per day when other strategies don't fire."""

    STRATEGY_NAME = "KEEPALIVE"
    KEEPALIVE_HOUR_UTC = 18
    POSITION_SIZE_PCT = 0.05

    def __init__(self, cmc: CMCHubClient, validator: TokenValidator):
        self.cmc = cmc
        self.validator = validator

    async def get_highest_volume_token(self) -> Optional[str]:
        """Pick eligible token with highest recent volume."""
        best_token = None
        best_volume = 0.0

        for token in VOLUME_CANDIDATES:
            if not self.validator.is_eligible(token):
                continue
            try:
                ohlcv = await self.cmc.get_ohlcv(token, interval="1h", limit=24)
                volume = sum(ohlcv.get("volume", [])[-24:])
                if volume > best_volume:
                    best_volume = volume
                    best_token = token
            except Exception as e:
                logger.debug("Volume check failed for %s: %s", token, e)

        return best_token or "USDT"

    async def generate_signal(self, portfolio: dict) -> Optional[TradeSignal]:
        now = datetime.now(timezone.utc)
        if portfolio.get("trades_today", 0) > 0:
            return None
        if now.hour < self.KEEPALIVE_HOUR_UTC:
            return None

        top_token = await self.get_highest_volume_token()
        if not self.validator.is_eligible(top_token):
            logger.warning("Keepalive token %s not eligible", top_token)
            return None

        return TradeSignal(
            strategy=self.STRATEGY_NAME,
            action="BUY",
            token=top_token,
            token_to="USDT",
            confidence=0.5,
            expected_return=0.001,
            risk=0.05,
            position_size_pct=self.POSITION_SIZE_PCT,
            reason=f"Daily minimum trade requirement (highest volume: {top_token})",
            stop_loss_pct=0.01,
            take_profit_pct=0.02,
        )

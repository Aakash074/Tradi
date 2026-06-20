"""Strategy 1: Market State Adapter — adaptive strategy based on market regime."""

import logging
from typing import Optional

from data.cmchub_client import CMCHubClient
from strategies.regime_detection import MarketRegime, detect_regime
from strategies.signal_generation import TradeSignal
from strategies.technical import adx, rsi, supertrend
from validation.token_validator import TokenValidator

logger = logging.getLogger(__name__)

HIGH_LIQUIDITY_TOKENS = ["CAKE", "ETH", "DOGE", "SHIB", "BNB", "USDT", "USDC", "LINK", "AVAX"]
TOP_MCAP_TOKENS = [
    "ETH", "USDT", "USDC", "XRP", "DOGE", "ADA", "LINK", "AVAX", "SHIB",
    "DOT", "UNI", "AAVE", "ATOM", "FIL", "INJ", "CAKE", "LTC", "BCH", "TON", "DAI",
]

SCAN_TOKENS = [
    "CAKE", "ETH", "DOGE", "SHIB", "LINK", "BNB", "ADA",
    "AVAX", "DOT", "UNI", "AAVE", "ATOM", "FIL", "INJ",
    "LTC", "BCH", "TON", "DAI", "USDT", "USDC",
]

STATE_PARAMS = {
    MarketRegime.TRENDING: {"size": 0.15, "stop": 0.02, "tp": 0.06, "risk": 1.0},
    MarketRegime.RANGING: {"size": 0.10, "stop": 0.015, "tp": 0.045, "risk": 0.8},
    MarketRegime.VOLATILE: {"size": 0.08, "stop": 0.015, "tp": 0.09, "risk": 1.5},
    MarketRegime.ACCUMULATION: {"size": 0.05, "stop": 0.0, "tp": 0.0, "risk": 0.5},
}


class MarketStateAdapter:
    """Primary strategy (60% allocation) — adapts tactics by market state."""

    ALLOCATION = 0.60
    STRATEGY_NAME = "ADAPTER"

    def __init__(self, cmc: CMCHubClient, validator: TokenValidator):
        self.cmc = cmc
        self.validator = validator
        self.current_regime: MarketRegime = MarketRegime.ACCUMULATION
        self.regime_confirmed_at: Optional[str] = None
        self.pending_regime: Optional[MarketRegime] = None
        self._last_metrics: dict = {}

    async def detect_and_update_regime(self, symbol: str = "CAKE") -> MarketRegime:
        ohlcv = await self.cmc.get_ohlcv(symbol, interval="1h", limit=100)
        regime, metrics = detect_regime(
            ohlcv["high"], ohlcv["low"], ohlcv["close"]
        )
        self._last_metrics = metrics
        if regime != self.current_regime:
            if self.pending_regime == regime:
                self.current_regime = regime
                self.pending_regime = None
                logger.info("Market state confirmed: %s metrics=%s", regime.value, metrics)
            else:
                self.pending_regime = regime
                logger.info("Market state change pending: %s -> %s", self.current_regime.value, regime.value)
        return self.current_regime

    async def generate_signal(self, symbol: str = "CAKE") -> Optional[TradeSignal]:
        if not self.validator.is_eligible(symbol):
            logger.warning("Market state adapter signal rejected: %s not eligible", symbol)
            return None

        regime = await self.detect_and_update_regime(symbol)
        ohlcv = await self.cmc.get_ohlcv(symbol, interval="1h", limit=100)
        close = ohlcv["close"]
        high, low = ohlcv["high"], ohlcv["low"]
        volume = ohlcv["volume"]
        params = STATE_PARAMS[regime]

        if regime == MarketRegime.TRENDING:
            return self._trending_signal(symbol, high, low, close, params)
        if regime == MarketRegime.RANGING:
            return self._ranging_signal(symbol, close, params)
        if regime == MarketRegime.VOLATILE:
            return self._volatile_signal(symbol, close, volume, params)
        return self._accumulation_signal(symbol, close, params)

    def _trending_signal(
        self, symbol: str, high: list, low: list, close: list, params: dict
    ) -> Optional[TradeSignal]:
        if symbol not in HIGH_LIQUIDITY_TOKENS and symbol != "CAKE":
            return None
        _, bullish = supertrend(high, low, close)
        adx_vals = adx(high, low, close)
        if not bullish or not adx_vals:
            return None
        if bullish[-1] and adx_vals[-1] > 20:
            return TradeSignal(
                strategy=self.STRATEGY_NAME,
                action="BUY",
                token=symbol,
                token_to="USDT",
                confidence=0.75,
                expected_return=params["tp"],
                risk=params["risk"],
                position_size_pct=params["size"],
                reason=f"Supertrend bullish in TRENDING state, ADX={adx_vals[-1]:.1f}",
                stop_loss_pct=params["stop"],
                take_profit_pct=params["tp"],
            )
        return None

    def _ranging_signal(self, symbol: str, close: list, params: dict) -> Optional[TradeSignal]:
        rsi_vals = rsi(close)
        if not rsi_vals or rsi_vals[-1] >= 40:
            return None
        return TradeSignal(
            strategy=self.STRATEGY_NAME,
            action="BUY",
            token=symbol,
            token_to="USDT",
            confidence=0.65,
            expected_return=params["tp"],
            risk=params["risk"],
            position_size_pct=params["size"],
            reason=f"RSI oversold ({rsi_vals[-1]:.1f}) in RANGING state",
            stop_loss_pct=params["stop"],
            take_profit_pct=params["tp"],
        )

    def _volatile_signal(
        self, symbol: str, close: list, volume: list, params: dict
    ) -> Optional[TradeSignal]:
        from strategies.technical import bollinger_bands

        upper, _, _ = bollinger_bands(close)
        if not upper or len(volume) < 20:
            return None
        avg_vol = sum(volume[-20:]) / 20
        if close[-1] > upper[-1] and volume[-1] > 1.2 * avg_vol:
            return TradeSignal(
                strategy=self.STRATEGY_NAME,
                action="BUY",
                token=symbol,
                token_to="USDT",
                confidence=0.70,
                expected_return=params["tp"],
                risk=params["risk"],
                position_size_pct=params["size"],
                reason="Bollinger breakout with volume spike in VOLATILE state",
                stop_loss_pct=params["stop"],
                take_profit_pct=params["tp"],
            )
        return None

    def _accumulation_signal(self, symbol: str, close: list, params: dict) -> Optional[TradeSignal]:
        if symbol not in TOP_MCAP_TOKENS:
            return None
        from strategies.technical import ema

        ema200 = ema(close, 200) if len(close) >= 200 else ema(close, min(50, len(close)))
        if not ema200:
            return None
        price_near_ema = abs(close[-1] - ema200[-1]) / ema200[-1] < 0.03
        if price_near_ema:
            return TradeSignal(
                strategy=self.STRATEGY_NAME,
                action="BUY",
                token=symbol,
                token_to="USDT",
                confidence=0.55,
                expected_return=0.02,
                risk=params["risk"],
                position_size_pct=params["size"],
                reason="DCA near 200 EMA in ACCUMULATION state",
                stop_loss_pct=0,
                take_profit_pct=0,
            )
        return None

    async def scan_opportunities(self) -> list[TradeSignal]:
        signals = []
        tokens_to_scan = SCAN_TOKENS
        for token in tokens_to_scan:
            if not self.validator.is_eligible(token):
                continue
            signal = await self.generate_signal(token)
            if signal:
                signals.append(signal)
        return signals

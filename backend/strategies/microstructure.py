"""Momentum pullback V3 — ADX trend filter + tournament top-20 universe."""

from typing import Optional

from data.cmchub_client import CMCHubClient
from strategies.technical import adx, ema, rsi

DEFAULT_ADX_THRESHOLD = 30.0


def momentum_pullback_from_ohlcv(
    ohlcv: dict,
    adx_threshold: float = DEFAULT_ADX_THRESHOLD,
    token: Optional[str] = None,
    top_momentum_tokens: Optional[set[str]] = None,
) -> tuple[bool, str, float]:
    """
    Strong-trend pullback: price > EMA20, ADX > threshold, RSI 30-50, volume > 1.2x avg.
    Rejects choppy markets (ADX < 20). Tournament: only tokens in top_momentum_tokens.
    """
    if token and top_momentum_tokens is not None and token not in top_momentum_tokens:
        return False, "NOT_IN_TOP_MOMENTUM", 0.0

    high = ohlcv.get("high", [])
    low = ohlcv.get("low", [])
    close = ohlcv.get("close", [])
    volume = ohlcv.get("volume", [])

    if len(close) < 30:
        return False, "NO_SIGNAL", 0.0

    adx_vals = adx(high, low, close, 14)
    ema20 = ema(close, 20)
    rsi_vals = rsi(close)
    if not adx_vals or not ema20 or not rsi_vals:
        return False, "NO_SIGNAL", 0.0

    adx_now = adx_vals[-1]
    if adx_now < 20:
        return False, "CHOPPY_MARKET", 0.0

    trend = close[-1] > ema20[-1] and adx_now > adx_threshold
    rsi_now = rsi_vals[-1]
    pullback = 30 < rsi_now < 50
    avg_vol = sum(volume[-20:]) / min(20, len(volume))
    vol_ok = volume[-1] > 1.2 * avg_vol if avg_vol > 0 else False

    strength = 0.0
    if trend:
        strength += 0.40
    if pullback:
        strength += 0.30
    if vol_ok:
        strength += 0.30
    if adx_now > 35:
        strength = min(1.0, strength + 0.1)

    if trend and pullback and vol_ok:
        return True, "STRONG_TREND_PULLBACK", min(1.0, strength)

    if strength >= 0.6:
        return True, "STRONG_TREND_PULLBACK_PARTIAL", strength

    return False, "NO_SIGNAL", strength


async def simple_momentum_strategy(
    cmc: CMCHubClient,
    token: str,
    adx_threshold: float = DEFAULT_ADX_THRESHOLD,
    top_momentum_tokens: Optional[set[str]] = None,
) -> tuple[bool, str, float]:
    ohlcv = await cmc.get_ohlcv(token, interval="1h", limit=50)
    return momentum_pullback_from_ohlcv(
        ohlcv,
        adx_threshold=adx_threshold,
        token=token,
        top_momentum_tokens=top_momentum_tokens,
    )


def calculate_strength(ohlcv: dict, adx_threshold: float = DEFAULT_ADX_THRESHOLD) -> float:
    _, _, strength = momentum_pullback_from_ohlcv(ohlcv, adx_threshold=adx_threshold)
    return strength

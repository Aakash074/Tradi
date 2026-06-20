"""Technical analysis indicators for Tradi strategies."""

from dataclasses import dataclass

import numpy as np


@dataclass
class OHLCV:
    open: list[float]
    high: list[float]
    low: list[float]
    close: list[float]
    volume: list[float]


def sma(values: list[float], period: int) -> list[float]:
    if len(values) < period:
        return []
    arr = np.array(values, dtype=float)
    result = np.convolve(arr, np.ones(period) / period, mode="valid")
    return result.tolist()


def ema(values: list[float], period: int) -> list[float]:
    if len(values) < period:
        return []
    arr = np.array(values, dtype=float)
    multiplier = 2 / (period + 1)
    ema_vals = [float(arr[0])]
    for price in arr[1:]:
        ema_vals.append((price - ema_vals[-1]) * multiplier + ema_vals[-1])
    return ema_vals


def rsi(values: list[float], period: int = 14) -> list[float]:
    if len(values) < period + 1:
        return []
    deltas = np.diff(values)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))
    rsis: list[float] = []
    for i in range(period, len(deltas)):
        if i > period:
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsis.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsis.append(100 - (100 / (1 + rs)))
    return rsis


def atr(high: list[float], low: list[float], close: list[float], period: int = 14) -> list[float]:
    if len(close) < period + 1:
        return []
    trs: list[float] = []
    for i in range(1, len(close)):
        tr = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        )
        trs.append(tr)
    return sma(trs, period)


def bollinger_bands(
    values: list[float], period: int = 20, std_dev: float = 2.0
) -> tuple[list[float], list[float], list[float]]:
    if len(values) < period:
        return [], [], []
    middle = sma(values, period)
    upper, lower = [], []
    for i in range(len(middle)):
        window = values[i : i + period]
        std = float(np.std(window))
        upper.append(middle[i] + std_dev * std)
        lower.append(middle[i] - std_dev * std)
    return upper, middle, lower


def bollinger_width(values: list[float], period: int = 20) -> list[float]:
    upper, middle, lower = bollinger_bands(values, period)
    if not middle:
        return []
    return [(u - l) / m if m else 0 for u, l, m in zip(upper, lower, middle)]


def adx(high: list[float], low: list[float], close: list[float], period: int = 14) -> list[float]:
    if len(close) < period * 2:
        return []
    plus_dm, minus_dm, tr_list = [], [], []
    for i in range(1, len(close)):
        up = high[i] - high[i - 1]
        down = low[i - 1] - low[i]
        plus_dm.append(up if up > down and up > 0 else 0)
        minus_dm.append(down if down > up and down > 0 else 0)
        tr_list.append(
            max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
        )
    if len(tr_list) < period:
        return []
    smoothed_tr = sum(tr_list[:period])
    smoothed_plus = sum(plus_dm[:period])
    smoothed_minus = sum(minus_dm[:period])
    adx_vals: list[float] = []
    for i in range(period, len(tr_list)):
        if i > period:
            smoothed_tr = smoothed_tr - smoothed_tr / period + tr_list[i]
            smoothed_plus = smoothed_plus - smoothed_plus / period + plus_dm[i]
            smoothed_minus = smoothed_minus - smoothed_minus / period + minus_dm[i]
        plus_di = 100 * smoothed_plus / smoothed_tr if smoothed_tr else 0
        minus_di = 100 * smoothed_minus / smoothed_tr if smoothed_tr else 0
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di) if (plus_di + minus_di) else 0
        adx_vals.append(dx)
    return adx_vals


def supertrend(
    high: list[float], low: list[float], close: list[float], period: int = 10, multiplier: float = 3.0
) -> tuple[list[float], list[bool]]:
    atr_vals = atr(high, low, close, period)
    if not atr_vals:
        return [], []
    offset = len(close) - len(atr_vals)
    st_line: list[float] = []
    bullish: list[bool] = []
    for i, a in enumerate(atr_vals):
        idx = i + offset
        hl2 = (high[idx] + low[idx]) / 2
        upper = hl2 + multiplier * a
        lower = hl2 - multiplier * a
        if i == 0:
            st_line.append(lower)
            bullish.append(True)
        else:
            prev = st_line[-1]
            if close[idx] > prev:
                st_line.append(max(lower, prev))
                bullish.append(True)
            else:
                st_line.append(min(upper, prev))
                bullish.append(False)
    return st_line, bullish

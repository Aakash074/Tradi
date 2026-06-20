"""Backtest engine for Tradi strategies."""

import random
from dataclasses import dataclass, field
from typing import Optional

from agent.risk_manager import RiskManager
from strategies.regime_detection import detect_regime
from strategies.signal_generation import TradeSignal, select_best_signal
from strategies.technical import adx, bollinger_bands, rsi, supertrend

SCAN_TOKENS = [
    "CAKE", "ETH", "DOGE", "SHIB", "LINK", "BNB", "ADA",
    "AVAX", "DOT", "UNI", "AAVE", "ATOM", "FIL", "INJ",
    "LTC", "BCH", "TON", "DAI", "USDT", "USDC",
]


@dataclass
class BacktestResult:
    days: int
    strategy: str
    initial_value: float
    final_value: float
    total_return_pct: float
    max_drawdown_pct: float
    trade_count: int
    win_rate_pct: float
    keepalive_trades: int = 0
    equity_curve: list[float] = field(default_factory=list)
    drawdown_curve: list[float] = field(default_factory=list)


def _generate_ohlcv(bars: int, seed: int, drift: float = 0.0002, vol: float = 0.012) -> dict:
    rng = random.Random(seed)
    price = 100.0
    o, h, l, c, v = [], [], [], [], []
    for _ in range(bars):
        change = drift + rng.gauss(0, vol)
        open_p = price
        close_p = max(0.01, price * (1 + change))
        high_p = max(open_p, close_p) * (1 + abs(rng.gauss(0, 0.004)))
        low_p = min(open_p, close_p) * (1 - abs(rng.gauss(0, 0.004)))
        volume = rng.uniform(500_000, 2_000_000)
        o.append(open_p)
        h.append(high_p)
        l.append(low_p)
        c.append(close_p)
        v.append(volume)
        price = close_p
    return {"open": o, "high": h, "low": l, "close": c, "volume": v}


def _adapter_signal(regime: str, ohlcv: dict, token: str = "CAKE") -> Optional[TradeSignal]:
    high, low, close, volume = ohlcv["high"], ohlcv["low"], ohlcv["close"], ohlcv["volume"]
    params = {
        "TRENDING": {"size": 0.15, "stop": 0.02, "tp": 0.06, "risk": 1.0},
        "RANGING": {"size": 0.10, "stop": 0.015, "tp": 0.045, "risk": 0.8},
        "VOLATILE": {"size": 0.08, "stop": 0.015, "tp": 0.09, "risk": 1.5},
        "ACCUMULATION": {"size": 0.05, "stop": 0.0, "tp": 0.0, "risk": 0.5},
    }.get(regime, {"size": 0.05, "stop": 0.02, "tp": 0.04, "risk": 1.0})
    p = params

    if regime == "TRENDING":
        _, bullish = supertrend(high, low, close)
        adx_vals = adx(high, low, close)
        if bullish and adx_vals and bullish[-1] and adx_vals[-1] > 20:
            return TradeSignal("ADAPTER", "BUY", token, "USDT", 0.75, p["tp"], p["risk"], p["size"],
                               "Supertrend TRENDING", p["stop"], p["tp"])
    elif regime == "RANGING":
        rsi_vals = rsi(close)
        if rsi_vals and rsi_vals[-1] < 40:
            return TradeSignal("ADAPTER", "BUY", token, "USDT", 0.65, p["tp"], p["risk"], p["size"],
                               "RSI oversold RANGING", p["stop"], p["tp"])
    elif regime == "VOLATILE":
        upper, _, _ = bollinger_bands(close)
        if upper and len(volume) >= 20:
            avg_vol = sum(volume[-20:]) / 20
            if close[-1] > upper[-1] and volume[-1] > 1.2 * avg_vol:
                return TradeSignal("ADAPTER", "BUY", token, "USDT", 0.70, p["tp"], p["risk"], p["size"],
                                   "Bollinger VOLATILE", p["stop"], p["tp"])
    return None


def _momentum_signal(ohlcv: dict, token: str = "CAKE") -> Optional[TradeSignal]:
    high, low, close, volume = ohlcv["high"], ohlcv["low"], ohlcv["close"], ohlcv["volume"]
    period = 20
    if len(close) < period + 1:
        return None
    period_high = max(high[-(period + 1):-1])
    avg_vol = sum(volume[-20:]) / min(20, len(volume))
    if close[-1] <= period_high or volume[-1] < 1.2 * avg_vol:
        return None
    breakout_pct = (close[-1] - period_high) / period_high if period_high else 0
    return TradeSignal(
        "MOMENTUM", "BUY", token, "USDT",
        min(0.95, 0.65 + breakout_pct * 5), 0.12, 1.0, 0.15,
        f"Breakout above {period}p high", 0.03, 0.0,
    )


def _keepalive_signal(trades_today: int, hour_of_day: int) -> Optional[TradeSignal]:
    if trades_today > 0 or hour_of_day < 18:
        return None
    return TradeSignal(
        "KEEPALIVE", "BUY", "CAKE", "USDT", 0.5, 0.001, 0.05, 0.05,
        "Daily minimum trade requirement", 0.01, 0.02,
    )


def run_backtest(days: int = 90, strategy: str = "all", seed: int = 42) -> BacktestResult:
    bars_per_day = 24
    total_bars = days * bars_per_day
    window = 100
    initial = 10_000.0
    cash = initial
    peak = initial
    equity_curve = [initial]
    drawdown_curve = [0.0]
    trades = 0
    wins = 0
    keepalive_trades = 0
    position = None
    risk = RiskManager()
    trades_today = 0
    current_day = -1

    ohlcv_full = _generate_ohlcv(total_bars + window, seed=seed)

    for i in range(window, total_bars, 4):  # evaluate every 4 hours
        day = i // bars_per_day
        hour = i % bars_per_day
        if day != current_day:
            trades_today = 0
            current_day = day

        slice_ = {k: v[i - window + 1:i + 1] for k, v in ohlcv_full.items()}
        regime, _ = detect_regime(slice_["high"], slice_["low"], slice_["close"])
        drawdown = (peak - equity_curve[-1]) / peak if peak else 0

        if position:
            entry = position["entry"]
            current = slice_["close"][-1]
            pnl_pct = (current - entry) / entry
            hold_bars = i - position["bar"]
            stop = position.get("stop_pct", 0.03)
            if pnl_pct <= -stop or pnl_pct >= 0.06 or hold_bars >= 48:
                pnl_usd = position["size"] * pnl_pct
                cash += position["size"] + pnl_usd
                trades += 1
                if pnl_usd > 0:
                    wins += 1
                position = None

        signals: list[TradeSignal] = []
        if strategy in ("all", "adapter"):
            for token in SCAN_TOKENS:
                sig = _adapter_signal(regime.value, slice_, token)
                if sig:
                    signals.append(sig)
        if strategy in ("all", "momentum"):
            for token in SCAN_TOKENS:
                sig = _momentum_signal(slice_, token)
                if sig:
                    signals.append(sig)

        best = select_best_signal(signals, threshold=0.005)

        if not best and strategy in ("all", "keepalive"):
            best = _keepalive_signal(trades_today, hour)

        if best and position is None and cash > 0:
            can_trade, _ = risk.check_portfolio_risk(drawdown, 0, 0)
            if can_trade:
                if best.strategy == "KEEPALIVE":
                    size_pct = best.position_size_pct
                else:
                    size_pct = risk.calculate_dynamic_risk_budget_size(best.confidence, drawdown)
                trade_size = min(cash * size_pct, cash * 0.25)
                if trade_size > 50:
                    cash -= trade_size
                    position = {
                        "entry": slice_["close"][-1],
                        "size": trade_size,
                        "stop_pct": best.stop_loss_pct or 0.03,
                        "bar": i,
                    }
                    trades_today += 1
                    if best.strategy == "KEEPALIVE":
                        keepalive_trades += 1

        total = cash + (position["size"] if position else 0)
        peak = max(peak, total)
        equity_curve.append(total)
        drawdown_curve.append((peak - total) / peak * 100 if peak else 0)

    final = equity_curve[-1]
    return BacktestResult(
        days=days,
        strategy=strategy,
        initial_value=initial,
        final_value=round(final, 2),
        total_return_pct=round((final - initial) / initial * 100, 2),
        max_drawdown_pct=round(max(drawdown_curve), 2),
        trade_count=trades,
        win_rate_pct=round(wins / trades * 100, 1) if trades else 0,
        keepalive_trades=keepalive_trades,
        equity_curve=equity_curve,
        drawdown_curve=drawdown_curve,
    )

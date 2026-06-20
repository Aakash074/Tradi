"""Momentum pullback V3 backtest — asymmetric exits, vol sizing, ADX filter."""

import math
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from agent.correlation_guard import get_correlation_24h
from agent.exit_manager import apply_trailing_stop, set_exit_levels
from agent.russian_doll_risk import RussianDollRisk
from strategies.kelly_sizing import dynamic_sizing, position_size
from strategies.microstructure import momentum_pullback_from_ohlcv
from strategies.regime_filter import RegimeMode
from strategies.technical import atr

SCAN_TOKENS = [
    "CAKE", "ETH", "DOGE", "SHIB", "LINK", "BNB", "ADA",
    "AVAX", "DOT", "UNI", "AAVE", "ATOM", "FIL", "INJ",
    "LTC", "BCH", "TON",
]

TARGETS = {
    "sharpe_ratio": 1.8,
    "max_drawdown_pct": 15.0,
    "win_rate_pct": 48.0,
    "profit_factor": 1.6,
    "expectancy_per_trade_pct": 0.15,
}

MAX_POSITIONS = 4
MAX_NEW_PER_BAR = 4
MIN_STRENGTH = 0.6
ENFORCE_HOUR = 20
QUALIFICATION_SIZE = 0.005


@dataclass
class BacktestConfig:
    stop_loss_pct: float = 0.015
    take_profit_pct: float = 0.045
    adx_threshold: float = 25.0
    sizing_mode: str = "dynamic"  # dynamic | fixed


@dataclass
class MomentumBacktestResult:
    strategy: str
    start: str
    end: str
    initial_capital: float
    final_capital: float
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate_pct: float
    profit_factor: float
    expectancy_per_trade_pct: float
    trade_count: int
    qualification_trades: int
    targets_met: dict[str, bool]
    config: dict = field(default_factory=dict)
    equity_curve: list[float] = field(default_factory=list)
    daily_returns: list[float] = field(default_factory=list)
    trade_log: list[dict] = field(default_factory=list)


def _generate_token_series(bars: int, seed: int, drift: float = 0.0002) -> dict:
    rng = random.Random(seed)
    price = 50.0 + seed % 100
    o, h, l, c, v = [], [], [], [], []
    for _ in range(bars):
        change = drift + rng.gauss(0, 0.012)
        open_p = price
        close_p = max(0.01, price * (1 + change))
        high_p = max(open_p, close_p) * (1 + abs(rng.gauss(0, 0.004)))
        low_p = min(open_p, close_p) * (1 - abs(rng.gauss(0, 0.004)))
        volume = rng.uniform(400_000, 2_500_000)
        o.append(open_p)
        h.append(high_p)
        l.append(low_p)
        c.append(close_p)
        v.append(volume)
        price = close_p
    return {"open": o, "high": h, "low": l, "close": c, "volume": v}


def _regime_from_slice(slice_: dict, fng: float) -> RegimeMode:
    close = slice_["close"]
    if len(close) < 30:
        return RegimeMode.NORMAL
    rets = [(close[i] - close[i - 1]) / close[i - 1] for i in range(1, len(close))]
    vol_24h = (sum(r * r for r in rets[-24:]) / min(24, len(rets))) ** 0.5 if rets else 0.02
    vol_30d = (sum(r * r for r in rets) / len(rets)) ** 0.5 if rets else 0.02
    ratio = vol_24h / vol_30d if vol_30d > 0 else 1.0
    if ratio > 1.5 or fng < 20:
        return RegimeMode.DEFENSIVE
    if ratio < 0.7 and fng > 50:
        return RegimeMode.AGGRESSIVE
    return RegimeMode.NORMAL


def _atr_pct(ohlcv: dict) -> float:
    close = ohlcv["close"]
    atr_vals = atr(ohlcv["high"], ohlcv["low"], close, 14)
    if not atr_vals or not close:
        return 0.02
    return atr_vals[-1] / close[-1]


def _safest_token_at_bar(token_data: dict, bar: int, window: int) -> str:
    best, best_atr = SCAN_TOKENS[0], float("inf")
    for token in SCAN_TOKENS:
        sl = {k: v[bar - window + 1 : bar + 1] for k, v in token_data[token].items()}
        ap = _atr_pct(sl)
        if ap < best_atr:
            best_atr = ap
            best = token
    return best


def _passes_correlation(token: str, positions: list[dict]) -> bool:
    if len(positions) < 2:
        return True
    largest = max(positions, key=lambda p: p["size_usd"])
    corr = get_correlation_24h(token, largest["token"])
    return corr < 0.8


def run_momentum_backtest(
    start: str = "2024-01-01",
    end: str = "2026-01-01",
    capital: float = 10_000.0,
    strategy: str = "momentum_pullback",
    seed: int = 42,
    config: Optional[BacktestConfig] = None,
) -> MomentumBacktestResult:
    cfg = config or BacktestConfig()
    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end)
    days = (end_dt - start_dt).days
    bars_per_day = 6
    total_bars = days * bars_per_day
    window = 120

    rng = random.Random(seed)
    token_data = {
        t: _generate_token_series(total_bars + window, seed=seed + i, drift=0.00015 + i * 0.00002)
        for i, t in enumerate(SCAN_TOKENS)
    }

    cash = capital
    peak = capital
    equity_curve = [capital]
    daily_returns: list[float] = []
    last_day_value = capital
    positions: list[dict] = []
    trades: list[dict] = []
    qualification_trades = 0
    russian = RussianDollRisk(halt_at=0.25)
    trades_today = 0
    current_day = -1

    for bar in range(window, total_bars):
        day = bar // bars_per_day
        hour = (bar % bars_per_day) * 4
        if day != current_day:
            trades_today = 0
            current_day = day

        fng = 50 + 15 * math.sin(day / 45) + rng.gauss(0, 5)
        drawdown = (peak - equity_curve[-1]) / peak if peak else 0
        russian.check_drawdown(drawdown)

        # Exits — asymmetric 1:3 + trailing
        to_close = []
        for pos in positions:
            token = pos["token"]
            price = token_data[token]["close"][bar]

            if price <= pos["stop_loss"]:
                to_close.append((pos, "STOP_LOSS", price))
            elif price >= pos["take_profit"]:
                to_close.append((pos, "TAKE_PROFIT", price))
            else:
                new_stop = apply_trailing_stop(
                    price,
                    pos["entry_price"],
                    pos["stop_loss"],
                    pos["trailing_activation"],
                    pos["trailing_distance"],
                )
                if new_stop > pos["stop_loss"]:
                    pos["stop_loss"] = new_stop
                if bar - pos["entry_bar"] >= 48:
                    to_close.append((pos, "TIME_EXPIRED", price))

        for pos, reason, exit_price in to_close:
            pnl_pct = (exit_price - pos["entry_price"]) / pos["entry_price"]
            pnl_usd = pos["size_usd"] * pnl_pct
            cash += pos["size_usd"] + pnl_usd
            trades.append({
                "token": pos["token"],
                "pnl_pct": round(pnl_pct * 100, 3),
                "pnl_usd": round(pnl_usd, 2),
                "reason": reason,
            })
            positions.remove(pos)

        if russian.state.trading_halted:
            total = cash + sum(p["size_usd"] for p in positions)
            peak = max(peak, total)
            equity_curve.append(total)
            continue

        ref_slice = {k: v[bar - window + 1 : bar + 1] for k, v in token_data["CAKE"].items()}
        regime = _regime_from_slice(ref_slice, fng)

        candidates: list[tuple[str, float, float]] = []
        if regime != RegimeMode.DEFENSIVE:
            for token in SCAN_TOKENS:
                ohlcv = {k: v[bar - window + 1 : bar + 1] for k, v in token_data[token].items()}
                ok, _, strength = momentum_pullback_from_ohlcv(ohlcv, adx_threshold=cfg.adx_threshold)
                if strength > MIN_STRENGTH and (ok or strength >= 0.6):
                    atr_p = _atr_pct(ohlcv)
                    candidates.append((token, strength, atr_p))

            candidates.sort(key=lambda x: x[1], reverse=True)
            max_new = min(MAX_NEW_PER_BAR, russian.state.max_positions - len(positions))

            for token, strength, atr_p in candidates[: max_new * 2]:
                if len(positions) >= russian.state.max_positions:
                    break
                if not _passes_correlation(token, positions):
                    continue

                if cfg.sizing_mode == "dynamic":
                    size_pct = dynamic_sizing(atr_p, strength, regime, drawdown)
                else:
                    size_pct = position_size(strength, drawdown)
                size_pct *= russian.state.position_size_multiplier
                trade_usd = min(cash * size_pct, cash * 0.05)
                if trade_usd < 50 or trade_usd > cash:
                    continue

                price = token_data[token]["close"][bar]
                exits = set_exit_levels(
                    price,
                    stop_loss_pct=cfg.stop_loss_pct,
                    take_profit_pct=cfg.take_profit_pct,
                )
                cash -= trade_usd
                positions.append({
                    "token": token,
                    "entry_price": price,
                    "size_usd": trade_usd,
                    "stop_loss": exits.stop_loss,
                    "take_profit": exits.take_profit,
                    "trailing_activation": exits.trailing_activation,
                    "trailing_distance": exits.trailing_distance,
                    "entry_bar": bar,
                })
                trades_today += 1
                if len([p for p in positions if p["entry_bar"] == bar]) >= max_new:
                    break

        # Smart qualification: 0.5% on lowest-ATR token
        if trades_today == 0 and hour >= ENFORCE_HOUR and cash > 100:
            token = _safest_token_at_bar(token_data, bar, window)
            price = token_data[token]["close"][bar]
            trade_usd = min(cash * QUALIFICATION_SIZE, cash * 0.01)
            if trade_usd >= 25:
                exits = set_exit_levels(
                    price,
                    stop_loss_pct=cfg.stop_loss_pct,
                    take_profit_pct=cfg.take_profit_pct,
                )
                cash -= trade_usd
                positions.append({
                    "token": token,
                    "entry_price": price,
                    "size_usd": trade_usd,
                    "stop_loss": exits.stop_loss,
                    "take_profit": exits.take_profit,
                    "trailing_activation": exits.trailing_activation,
                    "trailing_distance": exits.trailing_distance,
                    "entry_bar": bar,
                })
                trades_today += 1
                qualification_trades += 1

        total = cash + sum(p["size_usd"] for p in positions)
        peak = max(peak, total)
        equity_curve.append(total)

        if bar % bars_per_day == 0 and bar > window:
            daily_ret = (total - last_day_value) / last_day_value if last_day_value else 0
            daily_returns.append(daily_ret)
            last_day_value = total

    final = equity_curve[-1]
    wins = [t for t in trades if t["pnl_usd"] > 0]
    losses = [t for t in trades if t["pnl_usd"] <= 0]
    gross_profit = sum(t["pnl_usd"] for t in wins) or 0.01
    gross_loss = abs(sum(t["pnl_usd"] for t in losses)) or 0.01
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    profit_factor = gross_profit / gross_loss
    expectancy = sum(t["pnl_pct"] for t in trades) / len(trades) if trades else 0

    if len(daily_returns) > 1:
        mean_ret = sum(daily_returns) / len(daily_returns)
        std_ret = (sum((r - mean_ret) ** 2 for r in daily_returns) / (len(daily_returns) - 1)) ** 0.5
        sharpe = (mean_ret / std_ret * math.sqrt(252)) if std_ret > 0 else 0
    else:
        sharpe = 0

    pk = capital
    dd_curve = []
    for v in equity_curve:
        pk = max(pk, v)
        dd_curve.append((pk - v) / pk * 100 if pk else 0)
    max_dd = max(dd_curve) if dd_curve else 0

    metrics = {
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "win_rate_pct": round(win_rate, 1),
        "profit_factor": round(profit_factor, 2),
        "expectancy_per_trade_pct": round(expectancy, 3),
    }
    targets_met = {
        "sharpe_ratio": metrics["sharpe_ratio"] > TARGETS["sharpe_ratio"],
        "max_drawdown_pct": metrics["max_drawdown_pct"] < TARGETS["max_drawdown_pct"],
        "win_rate_pct": metrics["win_rate_pct"] > TARGETS["win_rate_pct"],
        "profit_factor": metrics["profit_factor"] > TARGETS["profit_factor"],
        "expectancy_per_trade_pct": metrics["expectancy_per_trade_pct"] > TARGETS["expectancy_per_trade_pct"],
    }

    return MomentumBacktestResult(
        strategy=strategy,
        start=start,
        end=end,
        initial_capital=capital,
        final_capital=round(final, 2),
        total_return_pct=round((final - capital) / capital * 100, 2),
        sharpe_ratio=metrics["sharpe_ratio"],
        max_drawdown_pct=metrics["max_drawdown_pct"],
        win_rate_pct=metrics["win_rate_pct"],
        profit_factor=metrics["profit_factor"],
        expectancy_per_trade_pct=metrics["expectancy_per_trade_pct"],
        trade_count=len(trades),
        qualification_trades=qualification_trades,
        config={
            "asymmetric_exits": f"{cfg.stop_loss_pct * 100:.1f}:{cfg.take_profit_pct * 100:.1f}",
            "adx_filter": cfg.adx_threshold,
            "sizing": cfg.sizing_mode,
        },
        targets_met=targets_met,
        equity_curve=equity_curve[:: max(1, len(equity_curve) // 500)],
        daily_returns=daily_returns,
        trade_log=trades[-100:],
    )

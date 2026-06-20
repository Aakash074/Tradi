"""Two-year confluence backtest — microstructure + Kelly + ghost validation."""

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from agent.ghost_tracker import GhostTracker
from agent.russian_doll_risk import RussianDollRisk
from strategies.kelly_sizing import kelly_size
from strategies.microstructure import (
    book_imbalance,
    count_bullish_signals,
    exchange_flow_signal,
    funding_edge,
    signal_strength,
)
from strategies.regime_filter import RegimeMode, kelly_multiplier
from strategies.technical import atr, bollinger_bands, rsi

SCAN_TOKENS = [
    "CAKE", "ETH", "DOGE", "SHIB", "LINK", "BNB", "ADA",
    "AVAX", "DOT", "UNI", "AAVE", "ATOM", "FIL", "INJ",
    "LTC", "BCH", "TON",
]

DEFAULT_STATS = {
    "FUNDING_FLOW": {"win_rate": 0.52, "avg_win": 0.04, "avg_loss": 0.02},
    "MICROSTRUCTURE_MR": {"win_rate": 0.50, "avg_win": 0.035, "avg_loss": 0.018},
    "KELLY_MOMENTUM": {"win_rate": 0.48, "avg_win": 0.06, "avg_loss": 0.025},
}

TARGETS = {
    "sharpe_ratio": 1.8,
    "max_drawdown_pct": 15.0,
    "win_rate_pct": 48.0,
    "profit_factor": 1.6,
    "expectancy_per_trade_pct": 0.15,
}


@dataclass
class ConfluenceBacktestResult:
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
    targets_met: dict[str, bool]
    equity_curve: list[float] = field(default_factory=list)
    daily_returns: list[float] = field(default_factory=list)
    trade_log: list[dict] = field(default_factory=list)


def _generate_token_series(bars: int, seed: int, drift: float = 0.00015) -> dict:
    rng = random.Random(seed)
    price = 50.0 + seed % 100
    o, h, l, c, v = [], [], [], [], []
    for _ in range(bars):
        change = drift + rng.gauss(0, 0.011)
        open_p = price
        close_p = max(0.01, price * (1 + change))
        high_p = max(open_p, close_p) * (1 + abs(rng.gauss(0, 0.003)))
        low_p = min(open_p, close_p) * (1 - abs(rng.gauss(0, 0.003)))
        volume = rng.uniform(400_000, 2_500_000)
        o.append(open_p)
        h.append(high_p)
        l.append(low_p)
        c.append(close_p)
        v.append(volume)
        price = close_p
    return {"open": o, "high": h, "low": l, "close": c, "volume": v}


def _synthetic_microstructure(ohlcv: dict, idx: int, rng: random.Random) -> dict:
    close = ohlcv["close"]
    if idx < 5:
        return {"funding_signal": "NEUTRAL", "funding_strength": 0, "flow_signal": "NEUTRAL",
                "flow_strength": 0, "book_imbalance": 0}

    ret_5 = (close[idx] - close[idx - 5]) / close[idx - 5]
    ret_1 = (close[idx] - close[idx - 1]) / close[idx - 1]

    funding_rate = -ret_5 * 3 + rng.gauss(0, 0.005)
    fund_sig, fund_str = funding_edge(funding_rate)

    inflow = max(1, 1_000_000 * (1 - ret_5 * 3 + rng.uniform(0.3, 1.0)))
    outflow = max(1, 1_000_000 * (1 + ret_5 * 3 + rng.uniform(1.0, 2.0)))
    flow_sig, flow_str = exchange_flow_signal(inflow, outflow)

    bid_size = 1000 * (1 + ret_1 * 25 + rng.uniform(0.5, 1.5))
    ask_size = 1000 * (1 - ret_1 * 25 + rng.uniform(0.5, 1.5))
    imbalance = book_imbalance([{"size": max(1, bid_size)}], [{"size": max(1, ask_size)}])

    return {
        "funding_signal": fund_sig,
        "funding_strength": fund_str,
        "flow_signal": flow_sig,
        "flow_strength": flow_str,
        "book_imbalance": imbalance,
    }


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


def run_confluence_backtest(
    start: str = "2024-01-01",
    end: str = "2026-01-01",
    capital: float = 10_000.0,
    strategy: str = "microstructure_kelly",
    seed: int = 42,
) -> ConfluenceBacktestResult:
    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end)
    days = (end_dt - start_dt).days
    bars_per_day = 6  # 4-hour bars
    total_bars = days * bars_per_day
    window = 120

    rng = random.Random(seed)
    token_data = {
        t: _generate_token_series(total_bars + window, seed=seed + i, drift=0.0001 + i * 0.00001)
        for i, t in enumerate(SCAN_TOKENS)
    }

    cash = capital
    peak = capital
    equity_curve = [capital]
    daily_returns: list[float] = []
    last_day_value = capital
    positions: list[dict] = []
    trades: list[dict] = []
    ghost = GhostTracker()
    russian = RussianDollRisk()
    max_positions = 4

    for bar in range(window, total_bars):
        day = bar // bars_per_day
        fng = 50 + 15 * math.sin(day / 45) + rng.gauss(0, 5)
        drawdown = (peak - equity_curve[-1]) / peak if peak else 0

        russian.check_drawdown(drawdown)
        if russian.state.trading_halted:
            total = cash + sum(p["size_usd"] for p in positions)
            peak = max(peak, total)
            equity_curve.append(total)
            continue

        # Layer 1 regime (once per bar, using reference token)
        ref_slice = {
            k: v[bar - window + 1 : bar + 1]
            for k, v in token_data["CAKE"].items()
        }
        regime = _regime_from_slice(ref_slice, fng)
        if regime == RegimeMode.DEFENSIVE:
            total = cash + sum(p["size_usd"] for p in positions)
            peak = max(peak, total)
            equity_curve.append(total)
            if bar % bars_per_day == 0 and bar > window:
                daily_ret = (total - last_day_value) / last_day_value if last_day_value else 0
                daily_returns.append(daily_ret)
                last_day_value = total
            continue

        # Exit management
        to_close = []
        for pos in positions:
            token = pos["token"]
            ohlcv = token_data[token]
            price = ohlcv["close"][bar]
            entry = pos["entry_price"]
            risk_pct = pos["risk_pct"]
            pnl_pct = (price - entry) / entry

            if price <= pos["stop_loss"]:
                to_close.append((pos, "STOP_LOSS", price))
            elif price >= pos["take_profit"]:
                to_close.append((pos, "TAKE_PROFIT", price))
            elif pnl_pct >= risk_pct * 1.5:
                trail = price * (1 - risk_pct)
                if trail > pos["stop_loss"]:
                    pos["stop_loss"] = trail
            elif bar - pos["entry_bar"] >= 48:
                to_close.append((pos, "TIME_EXPIRED", price))

        for pos, reason, exit_price in to_close:
            pnl_pct = (exit_price - pos["entry_price"]) / pos["entry_price"]
            pnl_usd = pos["size_usd"] * pnl_pct
            cash += pos["size_usd"] + pnl_usd
            ghost.resolve_ghost(pos["token"], exit_price)
            trades.append({
                "token": pos["token"],
                "strategy": pos["strategy"],
                "pnl_pct": round(pnl_pct * 100, 3),
                "pnl_usd": round(pnl_usd, 2),
                "reason": reason,
            })
            positions.remove(pos)

        if len(positions) >= russian.state.max_positions:
            total = cash + sum(p["size_usd"] for p in positions)
            peak = max(peak, total)
            equity_curve.append(total)
            if bar % bars_per_day == 0 and bar > window:
                daily_ret = (total - last_day_value) / last_day_value if last_day_value else 0
                daily_returns.append(daily_ret)
                last_day_value = total
            continue

        for token in SCAN_TOKENS:
            if len(positions) >= russian.state.max_positions:
                break
            ohlcv = token_data[token]
            slice_ = {k: v[bar - window + 1:bar + 1] for k, v in ohlcv.items()}

            ms = _synthetic_microstructure(ohlcv, bar, rng)
            if count_bullish_signals(ms) < 2:
                continue

            strength = signal_strength(ms)
            price = ohlcv["close"][bar]

            # Strategy selection
            strat = "FUNDING_FLOW"
            rsi_vals = rsi(slice_["close"])
            if ms["funding_signal"] == "BULLISH_EDGE" and ms["flow_signal"] == "ACCUMULATION":
                strat = "FUNDING_FLOW"
            elif rsi_vals and rsi_vals[-1] < 40 and ms["book_imbalance"] > 0.3:
                strat = "MICROSTRUCTURE_MR"
            elif regime == RegimeMode.AGGRESSIVE:
                high = slice_["high"]
                close = slice_["close"]
                vol = slice_["volume"]
                if len(close) >= 21:
                    period_high = max(high[-21:-1])
                    avg_vol = sum(vol[-20:]) / 20
                    if close[-1] > period_high and vol[-1] > 1.2 * avg_vol:
                        strat = "KELLY_MOMENTUM"
                    else:
                        continue
                else:
                    continue
            else:
                if strat == "FUNDING_FLOW" and ms["funding_signal"] != "BULLISH_EDGE":
                    continue

            ghost_decision = ghost.evaluate_signal(token, max(strength, 0.75), price, strat)
            if ghost_decision != "EXECUTE":
                continue

            stats = DEFAULT_STATS[strat]
            size = kelly_size(
                stats["win_rate"], stats["avg_win"], stats["avg_loss"],
                drawdown, kelly_multiplier(regime),
            )
            weights = {"FUNDING_FLOW": 0.40, "MICROSTRUCTURE_MR": 0.35, "KELLY_MOMENTUM": 0.25}
            size *= russian.state.position_size_multiplier * weights[strat]
            if size < 0.01:
                continue

            trade_usd = min(cash * size, cash * 0.25)
            if trade_usd < 50 or trade_usd > cash:
                continue

            risk_pct = 0.01 if strat != "MICROSTRUCTURE_MR" else 0.015
            cash -= trade_usd
            positions.append({
                "token": token,
                "strategy": strat,
                "entry_price": price,
                "size_usd": trade_usd,
                "risk_pct": risk_pct,
                "stop_loss": price * (1 - risk_pct),
                "take_profit": price * (1 + risk_pct * 2),
                "entry_bar": bar,
            })
            break  # one entry per bar

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
    profit_factor = gross_profit / gross_loss if gross_loss else 0
    expectancy = sum(t["pnl_pct"] for t in trades) / len(trades) if trades else 0

    if len(daily_returns) > 1:
        mean_ret = sum(daily_returns) / len(daily_returns)
        std_ret = (sum((r - mean_ret) ** 2 for r in daily_returns) / (len(daily_returns) - 1)) ** 0.5
        sharpe = (mean_ret / std_ret * math.sqrt(252)) if std_ret > 0 else 0
    else:
        sharpe = 0

    dd_curve = []
    pk = capital
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

    return ConfluenceBacktestResult(
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
        targets_met=targets_met,
        equity_curve=equity_curve[::max(1, len(equity_curve) // 500)],
        daily_returns=daily_returns,
        trade_log=trades[-100:],
    )

#!/usr/bin/env python3
"""Plot V3 backtest results from tradi_backtest.json for submission decks."""

import argparse
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _drawdown_curve(equity: list[float]) -> list[float]:
    peak = equity[0]
    out: list[float] = []
    for v in equity:
        peak = max(peak, v)
        out.append((peak - v) / peak * 100 if peak else 0.0)
    return out


def plot_backtest(payload: dict, output: Path) -> None:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.patches import FancyBboxPatch

    equity = payload["equity_curve"]
    drawdown = _drawdown_curve(equity)
    initial = payload["initial_capital"]
    start = payload.get("start", "2024-01-01")
    end = payload.get("end", "2026-01-01")
    cfg = payload.get("config", {})

    t0 = datetime.strptime(start, "%Y-%m-%d")
    t1 = datetime.strptime(end, "%Y-%m-%d")
    span_days = (t1 - t0).days
    dates = [t0 + (t1 - t0) * (i / max(len(equity) - 1, 1)) for i in range(len(equity))]

    ret = payload["total_return_pct"]
    max_dd = payload["max_drawdown_pct"]
    sharpe = payload["sharpe_ratio"]
    trades = payload["trade_count"]
    win_rate = payload["win_rate_pct"]
    exits = cfg.get("asymmetric_exits", "1.5:4.5")
    adx = cfg.get("adx_filter", 25)

    plt.style.use("dark_background")
    fig = plt.figure(figsize=(14, 9), facecolor="#0b0e11")
    gs = fig.add_gridspec(3, 1, height_ratios=[2.2, 1.2, 0.6], hspace=0.28)

    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax3 = fig.add_subplot(gs[2])
    for ax in (ax1, ax2, ax3):
        ax.set_facecolor("#0b0e11")
        ax.tick_params(colors="#848e9c", labelsize=9)
        for spine in ax.spines.values():
            spine.set_color("#2b3139")

    ax1.plot(dates, equity, color="#f0b90b", linewidth=1.8, label="Equity")
    ax1.axhline(initial, color="#848e9c", linestyle="--", alpha=0.5, linewidth=1)
    ax1.fill_between(dates, initial, equity, where=[e >= initial for e in equity], alpha=0.08, color="#0ecb81")
    ax1.fill_between(dates, initial, equity, where=[e < initial for e in equity], alpha=0.08, color="#f6465d")
    ax1.set_ylabel("Portfolio (USD)", color="#eaecef", fontsize=10)
    ax1.set_title(
        f"Tradi V3 Momentum Pullback  |  {start} → {end}  |  Return: {ret:+.2f}%",
        color="#eaecef",
        fontsize=13,
        fontweight="bold",
        pad=12,
    )
    ax1.legend(loc="upper left", framealpha=0.2)
    ax1.grid(True, alpha=0.15, color="#2b3139")

    ax2.fill_between(dates, drawdown, color="#f6465d", alpha=0.45)
    ax2.plot(dates, drawdown, color="#f6465d", linewidth=0.8)
    ax2.axhline(25, color="#f0b90b", linestyle="--", linewidth=1, alpha=0.8, label="25% halt")
    ax2.axhline(30, color="#f6465d", linestyle="--", linewidth=1, alpha=0.9, label="30% DQ")
    ax2.set_ylabel("Drawdown (%)", color="#eaecef", fontsize=10)
    ax2.set_title(f"Max Drawdown: {max_dd:.2f}%", color="#eaecef", fontsize=11, pad=8)
    ax2.set_ylim(0, max(35, max(drawdown) * 1.25))
    ax2.legend(loc="upper right", framealpha=0.2, fontsize=8)
    ax2.grid(True, alpha=0.15, color="#2b3139")

    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=4))
    plt.setp(ax1.get_xticklabels(), visible=False)

    ax3.axis("off")
    metrics = [
        ("Sharpe", f"{sharpe:.2f}", "#0ecb81" if sharpe >= 1.8 else "#848e9c"),
        ("Max DD", f"{max_dd:.2f}%", "#0ecb81" if max_dd < 15 else "#f6465d"),
        ("Win Rate", f"{win_rate:.1f}%", "#848e9c"),
        ("Trades", f"{trades:,}", "#eaecef"),
        ("Exits", f"{exits} (1:3)", "#eaecef"),
        (f"ADX ≥", f"{adx:.0f}", "#eaecef"),
        ("Final", f"${payload['final_capital']:,.0f}", "#f0b90b"),
    ]
    x0 = 0.02
    for i, (label, value, color) in enumerate(metrics):
        col = i % 4
        row = i // 4
        x = x0 + col * 0.24
        y = 0.55 - row * 0.45
        box = FancyBboxPatch(
            (x, y - 0.08), 0.22, 0.35,
            boxstyle="round,pad=0.02",
            facecolor="#1e2329",
            edgecolor="#2b3139",
            transform=ax3.transAxes,
        )
        ax3.add_patch(box)
        ax3.text(x + 0.02, y + 0.12, label, color="#848e9c", fontsize=9, transform=ax3.transAxes)
        ax3.text(x + 0.02, y - 0.02, value, color=color, fontsize=12, fontweight="bold", transform=ax3.transAxes)

    ax3.text(
        0.98, 0.15,
        "BNB Hackathon Track 1  ·  149 eligible tokens  ·  Paper-validated",
        color="#848e9c",
        fontsize=8,
        ha="right",
        transform=ax3.transAxes,
    )

    fig.autofmt_xdate()
    output.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output, dpi=180, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"Chart saved: {output.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot Tradi V3 backtest chart")
    parser.add_argument("--input", default="results/tradi_backtest.json")
    parser.add_argument("--output", default="results/tradi_backtest_v3.png")
    parser.add_argument("--also-backend", action="store_true", help="Copy to backend/backtest_results.png")
    args = parser.parse_args()

    input_path = ROOT / args.input
    payload = json.loads(input_path.read_text())
    out = ROOT / args.output
    plot_backtest(payload, out)

    if args.also_backend:
        backend_out = ROOT / "backend" / "backtest_results.png"
        plot_backtest(payload, backend_out)


if __name__ == "__main__":
    main()

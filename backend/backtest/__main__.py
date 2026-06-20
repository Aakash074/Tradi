"""Run Tradi strategy backtests.

Usage:
    cd backend && python -m backtest --days 90 --strategy all --output backtest_results.png
"""

import argparse
import sys
from pathlib import Path

# Ensure backend root is on path when run as module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    parser = argparse.ArgumentParser(description="Tradi strategy backtest")
    parser.add_argument("--days", type=int, default=90, help="Backtest period in days")
    parser.add_argument(
        "--strategy",
        choices=["all", "adapter", "momentum"],
        default="all",
        help="Strategy to backtest",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="backtest_results.png",
        help="Output chart path",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    from backtest.engine import run_backtest

    result = run_backtest(days=args.days, strategy=args.strategy, seed=args.seed)

    print("\n=== Tradi Backtest Results ===")
    print(f"Period:        {result.days} days")
    print(f"Strategy:      {result.strategy}")
    print(f"Initial:       ${result.initial_value:,.2f}")
    print(f"Final:         ${result.final_value:,.2f}")
    print(f"Total Return:  {result.total_return_pct:+.2f}%")
    print(f"Max Drawdown:  {result.max_drawdown_pct:.2f}%")
    print(f"Trades:        {result.trade_count}")
    print(f"Win Rate:      {result.win_rate_pct:.1f}%")
    print(f"Keepalive:     {result.keepalive_trades} trades")

    if result.total_return_pct < 0:
        print("\n⚠ WARNING: Negative returns — review strategy parameters before competition.")
    if result.max_drawdown_pct > 30:
        print("\n⚠ WARNING: Max drawdown exceeds 30% — DISQUALIFICATION RISK.")

    try:
        import matplotlib.pyplot as plt

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
        days_x = [i / 24 for i in range(len(result.equity_curve))]

        ax1.plot(days_x, result.equity_curve, color="#f0b90b", linewidth=1.5, label="Equity")
        ax1.axhline(result.initial_value, color="#666", linestyle="--", alpha=0.5)
        ax1.set_ylabel("Portfolio ($)")
        ax1.set_title(f"Tradi Backtest — {result.strategy} ({result.days}d) | Return: {result.total_return_pct:+.1f}%")
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        ax2.fill_between(days_x, result.drawdown_curve, color="#ef4444", alpha=0.4)
        ax2.axhline(30, color="#ef4444", linestyle="--", label="30% DQ line")
        ax2.axhline(25, color="#f59e0b", linestyle="--", label="25% halt")
        ax2.set_ylabel("Drawdown (%)")
        ax2.set_xlabel("Days")
        ax2.set_title(f"Max Drawdown: {result.max_drawdown_pct:.1f}%")
        ax2.legend()
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()
        out = Path(args.output)
        plt.savefig(out, dpi=150, bbox_inches="tight")
        print(f"\nChart saved: {out.resolve()}")
    except ImportError:
        print("\nmatplotlib not installed — skipping chart (pip install matplotlib)")


if __name__ == "__main__":
    main()

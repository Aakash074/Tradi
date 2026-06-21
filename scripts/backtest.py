#!/usr/bin/env python3
"""Run Tradi backtest and report target metrics."""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from backtest.momentum_backtest import BacktestConfig, TARGETS, run_momentum_backtest  # noqa: E402

MOMENTUM_STRATEGIES = {"momentum_pullback", "momentum_pullback_v3"}


def _parse_asymmetric_exits(value: str) -> tuple[float, float]:
    """Parse '1.5:4.5' → (0.015, 0.045)."""
    parts = value.split(":")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("asymmetric_exits must be STOP:TARGET e.g. 1.5:4.5")
    stop_pct = float(parts[0]) / 100
    target_pct = float(parts[1]) / 100
    return stop_pct, target_pct


def main() -> None:
    parser = argparse.ArgumentParser(description="Tradi backtest")
    parser.add_argument("--strategy", default="momentum_pullback_v3")
    parser.add_argument("--universe", default="eligible_tokens")
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2026-01-01")
    parser.add_argument("--capital", type=float, default=10000)
    parser.add_argument("--output", default="results/tradi_backtest.json")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--asymmetric_exits",
        default="1.5:4.5",
        help="Stop:target percent ratio e.g. 1.5:4.5",
    )
    parser.add_argument("--adx_filter", type=float, default=25, help="ADX trend threshold")
    parser.add_argument(
        "--sizing",
        default="dynamic",
        choices=["dynamic", "aggressive", "fixed"],
        help="Position sizing mode",
    )
    args = parser.parse_args()

    stop_pct, target_pct = _parse_asymmetric_exits(args.asymmetric_exits)
    config = BacktestConfig(
        stop_loss_pct=stop_pct,
        take_profit_pct=target_pct,
        adx_threshold=args.adx_filter,
        sizing_mode=args.sizing,
    )

    if args.strategy in MOMENTUM_STRATEGIES:
        result = run_momentum_backtest(
            start=args.start,
            end=args.end,
            capital=args.capital,
            strategy=args.strategy,
            seed=args.seed,
            config=config,
        )
    else:
        from backtest.confluence_backtest import run_confluence_backtest

        result = run_confluence_backtest(
            start=args.start,
            end=args.end,
            capital=args.capital,
            strategy=args.strategy,
            seed=args.seed,
        )

    output_path = ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        **asdict(result),
        "targets": TARGETS,
        "universe": args.universe,
    }
    output_path.write_text(json.dumps(payload, indent=2))

    print(f"\nTradi Backtest ({args.start} → {args.end})")
    print("=" * 55)
    print(f"Strategy:        {args.strategy}")
    if hasattr(result, "config") and result.config:
        print(f"Exits:           {result.config.get('asymmetric_exits', args.asymmetric_exits)}")
        print(f"ADX filter:      {result.config.get('adx_filter', args.adx_filter)}")
        print(f"Sizing:          {result.config.get('sizing', args.sizing)}")
    print(f"Capital:         ${result.initial_capital:,.0f} → ${result.final_capital:,.0f}")
    print(f"Total Return:    {result.total_return_pct:+.2f}%")
    print(f"Trades:          {result.trade_count}")
    if hasattr(result, "qualification_trades"):
        print(f"Qualification:   {result.qualification_trades} daily enforcement trades")
    print()
    print(f"{'Metric':<28} {'Result':>10} {'Target':>10} {'Status':>8}")
    print("-" * 55)

    rows = [
        ("Sharpe Ratio", result.sharpe_ratio, f"> {TARGETS['sharpe_ratio']}", "sharpe_ratio"),
        ("Max Drawdown %", result.max_drawdown_pct, f"< {TARGETS['max_drawdown_pct']}", "max_drawdown_pct"),
        ("Win Rate %", result.win_rate_pct, f"> {TARGETS['win_rate_pct']}", "win_rate_pct"),
        ("Profit Factor", result.profit_factor, f"> {TARGETS['profit_factor']}", "profit_factor"),
        ("Expectancy / trade %", result.expectancy_per_trade_pct, f"> {TARGETS['expectancy_per_trade_pct']}", "expectancy_per_trade_pct"),
    ]
    passed = 0
    for label, value, target, key in rows:
        ok = result.targets_met[key]
        passed += int(ok)
        status = "PASS" if ok else "MISS"
        print(f"{label:<28} {value:>10} {target:>10} {status:>8}")

    print("-" * 55)
    print(f"Targets met: {passed}/5")
    print(f"Results saved to {output_path}")


if __name__ == "__main__":
    main()

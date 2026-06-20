#!/usr/bin/env python3
"""Run Tradi in tournament mode for a paper/live session."""

import argparse
import asyncio
import logging
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_tournament")


def _parse_duration(value: str) -> float:
    """Parse duration like 24h, 30m, 1d into seconds."""
    m = re.match(r"^(\d+(?:\.\d+)?)(h|m|d|s)$", value.strip().lower())
    if not m:
        raise argparse.ArgumentTypeError("duration must be like 24h, 30m, 1d")
    amount, unit = float(m.group(1)), m.group(2)
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return amount * multipliers[unit]


async def run_session(config_path: Path, mode: str, duration_seconds: float, cycle_seconds: int) -> None:
    os.environ["AGENT_MODE"] = mode

    from config import get_settings

    get_settings.cache_clear()

    from agent.orchestrator import TradiOrchestrator

    orch = TradiOrchestrator(tournament_config_path=config_path)
    await orch.initialize()

    cycles = max(1, int(duration_seconds / cycle_seconds))
    logger.info(
        "Running %s mode for %.0fs (%d cycles @ %ds)",
        mode,
        duration_seconds,
        cycles,
        cycle_seconds,
    )

    results = []
    for i in range(cycles):
        result = await orch.run_cycle()
        results.append(result)
        trades = result.get("trades_executed", 0)
        regime = result.get("regime_mode", "?")
        logger.info(
            "Cycle %d/%d — regime=%s signals=%s trades=%s",
            i + 1,
            cycles,
            regime,
            result.get("signals_count", 0),
            trades,
        )
        if i < cycles - 1:
            await asyncio.sleep(min(cycle_seconds, 2))  # fast-forward in paper test

    portfolio = orch.portfolio.to_dict()
    conf = orch.confluence.get_dashboard_data()

    print("\n" + "=" * 55)
    print("TOURNAMENT SESSION COMPLETE")
    print("=" * 55)
    print(f"Config:          {config_path}")
    print(f"Mode:            {mode}")
    print(f"Duration:        {duration_seconds:.0f}s ({cycles} cycles)")
    print(f"Portfolio value: ${portfolio['total_value_usd']:,.2f}")
    print(f"Total return:    {portfolio['total_return_pct']:+.2f}%")
    print(f"Drawdown:        {portfolio['drawdown_pct']:.2f}%")
    print(f"Trades today:    {portfolio['trades_today']}")
    if conf.get("tournament_config"):
        tc = conf["tournament_config"]
        print(f"Exits:           {tc.get('asymmetric_exits', '1.5:6.0')}")
        print(f"ADX filter:      {tc.get('adx_filter')}")
        print(f"Sizing:          {tc.get('sizing')}")
    if conf.get("token_universe"):
        uni = conf["token_universe"].get("universe", [])
        print(f"Top momentum:    {', '.join(uni[:8])}{'...' if len(uni) > 8 else ''}")
    print("=" * 55)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Tradi tournament mode")
    parser.add_argument("--config", default="config/tournament_week.yaml")
    parser.add_argument("--mode", default="paper", choices=["paper", "competition", "live"])
    parser.add_argument("--duration", default="24h", type=_parse_duration, help="e.g. 24h, 30m")
    parser.add_argument("--cycle-seconds", type=int, default=900, help="Seconds between cycles")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = ROOT / config_path

    asyncio.run(run_session(config_path, args.mode, args.duration, args.cycle_seconds))


if __name__ == "__main__":
    main()

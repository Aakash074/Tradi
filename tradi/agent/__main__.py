#!/usr/bin/env python3
"""Tradi agent CLI — paper/competition trading with structured logs."""

import argparse
import asyncio
import logging
import os
import re
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def _parse_duration(value: str) -> float:
    m = re.match(r"^(\d+(?:\.\d+)?)(h|m|d|s)$", value.strip().lower())
    if not m:
        raise argparse.ArgumentTypeError("duration must be like 48h, 30m, 1d")
    amount, unit = float(m.group(1)), m.group(2)
    return amount * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]


def _setup_logging(level: str, log_file: Optional[Path] = None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=LOG_FORMAT,
        handlers=handlers,
        force=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="tradi.agent", description="Tradi autonomous agent")
    parser.add_argument("--mode", default="paper", choices=["paper", "competition", "live"])
    parser.add_argument("--config", default="config/production.yaml")
    parser.add_argument("--duration", default="48h", type=_parse_duration)
    parser.add_argument("--live-cmc", action="store_true", help="Use live CMC API (requires CMC_API_KEY)")
    parser.add_argument("--x402", action="store_true", help="Enable x402 USDC micropayments for CMC premium MCP data")
    parser.add_argument("--serve-api", action="store_true", default=True, help="Serve dashboard API on :8000")
    parser.add_argument("--no-serve-api", action="store_false", dest="serve_api")
    parser.add_argument("--dry-run", action="store_true", help="Competition config with paper swaps + wallet sync")
    parser.add_argument("--cycle-seconds", type=int, default=900)
    parser.add_argument("--log-file", default=None, help="Optional log file path")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    os.environ["AGENT_MODE"] = args.mode
    if args.live_cmc:
        os.environ["LIVE_CMC"] = "1"
    if args.x402:
        os.environ["X402_ENABLED"] = "1"
    if args.dry_run:
        os.environ["COMPETITION_DRY_RUN"] = "1"

    from config import get_settings

    get_settings.cache_clear()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = ROOT / config_path

    log_file = Path(args.log_file) if args.log_file else None
    _setup_logging(args.log_level, log_file)

    try:
        import yaml

        with open(config_path) as f:
            raw = yaml.safe_load(f) or {}
        args.cycle_seconds = raw.get("agent", {}).get("cycle_seconds", args.cycle_seconds)
        log_level = raw.get("agent", {}).get("log_level", args.log_level)
        _setup_logging(log_level, log_file)
    except Exception:
        pass

    from agent_runner import run_agent_session, run_with_api

    if args.serve_api:
        asyncio.run(
            run_with_api(
                config_path=config_path,
                mode=args.mode,
                duration_seconds=args.duration,
                cycle_seconds=args.cycle_seconds,
                live_cmc=args.live_cmc,
                dry_run=args.dry_run,
            )
        )
    else:
        asyncio.run(
            run_agent_session(
                config_path=config_path,
                mode=args.mode,
                duration_seconds=args.duration,
                cycle_seconds=args.cycle_seconds,
                live_cmc=args.live_cmc,
                dry_run=args.dry_run,
                real_time=True,
            )
        )


if __name__ == "__main__":
    main()

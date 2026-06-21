"""Shared agent session runner for paper/competition trading."""

import asyncio
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agent.competition_scheduler import competition_bounds, scheduled_agent_mode
from agent.orchestrator import TradiOrchestrator
from config import get_settings
from tournament_config import DEFAULT_PRODUCTION_PATH, DEFAULT_TOURNAMENT_PATH, load_tournament_config

logger = logging.getLogger(__name__)


async def maybe_auto_switch_competition(
    orch: TradiOrchestrator,
    cli_mode: str,
) -> None:
    """Flip to competition mode at COMPETITION_START (UTC) without restart."""
    settings = get_settings()
    if not settings.competition_auto_switch:
        return

    target = scheduled_agent_mode(settings, cli_mode)
    if settings.agent_mode == target:
        return

    start, end = competition_bounds(settings)
    now = datetime.now(timezone.utc)

    if target == "competition":
        await orch.apply_agent_mode("competition", DEFAULT_TOURNAMENT_PATH)
        logger.info(
            "COMPETITION_AUTO_START utc=%s window=%s → %s",
            now.isoformat(),
            start.isoformat(),
            end.isoformat(),
        )
        return

    production_path = orch.production_config_path or DEFAULT_PRODUCTION_PATH
    await orch.apply_agent_mode("paper", production_path)
    logger.info(
        "COMPETITION_AUTO_END utc=%s window_ended=%s",
        now.isoformat(),
        end.isoformat(),
    )


async def run_agent_session(
    config_path: Path,
    mode: str = "paper",
    duration_seconds: float = 86400,
    cycle_seconds: int = 900,
    live_cmc: bool = False,
    dry_run: bool = False,
    real_time: bool = True,
    orchestrator: Optional[TradiOrchestrator] = None,
) -> TradiOrchestrator:
    """
    Run the agent loop for a configured duration.
    real_time=True sleeps full cycle_seconds between cycles (production paper).
    """
    agent_config = load_tournament_config(config_path)
    orch = orchestrator
    if orch is None:
        orch = TradiOrchestrator(
            tournament_config_path=config_path,
            live_cmc=live_cmc,
            dry_run=dry_run,
        )
        await orch.initialize()
        await maybe_auto_switch_competition(orch, cli_mode=mode)

        label = "PRODUCTION" if "production" in config_path.name else "TOURNAMENT"
        logger.info(
            "%s MODE ACTIVE | strategy=%s exits=%s adx=%s sizing=%s live_cmc=%s",
            label,
            agent_config.strategy,
            agent_config.asymmetric_exits,
            agent_config.adx_filter,
            agent_config.sizing,
            live_cmc,
        )

    orch._running = True
    deadline = time.monotonic() + duration_seconds
    cycle_num = 0

    while time.monotonic() < deadline and orch._running:
        cycle_num += 1
        await maybe_auto_switch_competition(orch, cli_mode=mode)

        agent_config = orch.tournament_config
        if agent_config is None:
            agent_config = load_tournament_config(config_path)

        portfolio = orch.portfolio.to_dict()
        dd = portfolio["drawdown_pct"]
        if dd >= 5:
            logger.info("DRAWDOWN portfolio_dd=%.2f%% value=$%.2f", dd, portfolio["total_value_usd"])
        if dd >= agent_config.halt_drawdown * 100:
            logger.warning("HALT drawdown=%.2f%% threshold=%.0f%%", dd, agent_config.halt_drawdown * 100)

        daily = portfolio["daily_pnl_pct"]
        if daily <= -agent_config.daily_loss_limit * 100:
            logger.warning(
                "DAILY daily_pnl=%.2f%% limit=%.0f%%",
                daily,
                agent_config.daily_loss_limit * 100,
            )

        try:
            result = await orch.run_cycle()
            trades = result.get("trades_executed", 0)
            logger.info(
                "CYCLE %d regime=%s signals=%d trades=%d",
                cycle_num,
                result.get("regime_mode", "?"),
                result.get("signals_count", 0),
                trades,
            )
        except Exception as e:
            logger.error("ERROR cycle=%d msg=%s", cycle_num, e, exc_info=True)

        if time.monotonic() >= deadline:
            break
        sleep_s = cycle_seconds if real_time else min(cycle_seconds, 2)
        await asyncio.sleep(sleep_s)

    portfolio = orch.portfolio.to_dict()
    logger.info(
        "SESSION_END cycles=%d value=$%.2f return=%.2f%% drawdown=%.2f%% trades_today=%d",
        cycle_num,
        portfolio["total_value_usd"],
        portfolio["total_return_pct"],
        portfolio["drawdown_pct"],
        portfolio["trades_today"],
    )
    return orch


async def run_with_api(
    config_path: Path,
    mode: str,
    duration_seconds: float,
    cycle_seconds: int,
    live_cmc: bool,
    dry_run: bool = False,
    host: str = "0.0.0.0",
    port: int = 8000,
) -> None:
    """Run agent loop alongside FastAPI dashboard backend."""
    import uvicorn

    import main as api_main

    orch = TradiOrchestrator(
        tournament_config_path=config_path,
        live_cmc=live_cmc,
        dry_run=dry_run,
    )
    await orch.initialize()
    api_main.orchestrator = orch
    await maybe_auto_switch_competition(orch, cli_mode=mode)

    config = uvicorn.Config(api_main.app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    api_task = asyncio.create_task(server.serve())

    label = "PRODUCTION" if "production" in config_path.name else "TOURNAMENT"
    logger.info("%s MODE ACTIVE — API http://%s:%d", label, host, port)

    try:
        await run_agent_session(
            config_path=config_path,
            mode=mode,
            duration_seconds=duration_seconds,
            cycle_seconds=cycle_seconds,
            live_cmc=live_cmc,
            dry_run=dry_run,
            real_time=True,
            orchestrator=orch,
        )
    finally:
        server.should_exit = True
        await api_task

"""BSC gas defer and min ATR conviction filter."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.confluence_engine import ConfluenceEngine
from tournament_config import load_tournament_config

ROOT = Path(__file__).resolve().parents[2]


def _engine_with_gas(max_gas: float = 8.0):
    cmc = MagicMock()
    tournament = MagicMock()
    tournament.halt_drawdown = 0.2
    tournament.adx_filter = 20
    tournament.sizing = "aggressive"
    tournament.stop_loss_pct = 0.015
    tournament.take_profit_pct = 0.06
    tournament.daily_loss_limit = 0.05
    tournament.min_atr_pct = 0.0
    tournament.max_gas_gwei = max_gas
    tournament.universe = "all"
    tournament.top_n_tokens = 20

    engine = ConfluenceEngine(cmc, MagicMock(), tournament=tournament)
    engine.regime_mode = __import__(
        "strategies.regime_filter", fromlist=["RegimeMode"]
    ).RegimeMode.NORMAL
    engine.regime_metrics = {"fear_greed": 50}
    return engine


def test_tournament_yaml_loads_min_atr_and_gas():
    cfg = load_tournament_config(ROOT / "config" / "tournament_week.yaml")
    assert cfg.min_atr_pct == pytest.approx(0.02)
    assert cfg.max_gas_gwei == pytest.approx(8.0)


def test_entry_signal_low_conviction_min_atr():
    cmc = MagicMock()
    engine = ConfluenceEngine(cmc, MagicMock(), account_size=10_000)
    engine.min_atr_pct = 0.02
    ohlcv = {
        "open": [100.0] * 50,
        "high": [100.2] * 50,
        "low": [99.8] * 50,
        "close": [100.0] * 50,
        "volume": [1_000_000.0] * 50,
    }
    ok, _, _ = engine.entry_signal("CAKE", ohlcv, ohlcv, 100.0)
    assert ok is False


def test_should_enter_high_gas_strategy_only():
    engine = _engine_with_gas()

    async def run():
        with patch("agent.confluence_engine.get_bsc_gas_gwei", AsyncMock(return_value=12.0)):
            return await engine.should_enter(
                "CAKE", 0.8, 0.0, 0.02, [], 0.0, size_pct=0.05
            )

    ok, _, reason = asyncio.run(run())
    assert ok is False
    assert reason == "HIGH_GAS"


def test_should_enter_gas_fail_open():
    engine = _engine_with_gas()

    async def run():
        with patch("agent.confluence_engine.get_bsc_gas_gwei", AsyncMock(return_value=None)):
            return await engine.should_enter(
                "CAKE", 0.8, 0.0, 0.02, [], 0.0, size_pct=0.05
            )

    ok, _, reason = asyncio.run(run())
    assert ok is True
    assert reason != "HIGH_GAS"

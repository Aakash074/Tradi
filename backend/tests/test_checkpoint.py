"""Tests for agent session checkpoint save/load."""

import json
from pathlib import Path
from unittest.mock import MagicMock

from agent.checkpoint import (
    CHECKPOINT_VERSION,
    build_checkpoint,
    load_checkpoint,
    save_checkpoint,
)
from agent.portfolio import PortfolioTracker


def _mock_orch(tmp_path: Path, mode: str = "paper", dry_run: bool = False):
    orch = MagicMock()
    orch.portfolio = PortfolioTracker(10_000.0)
    orch.portfolio.state.trades_today = 2
    orch.portfolio.state.last_trade_date = "2026-06-21"
    orch._open_positions = [
        {
            "token": "CAKE",
            "token_to": "CAKE",
            "amount_usd": 500.0,
            "entry_price": 2.0,
            "current_price": 2.1,
            "stop_loss": 1.97,
            "take_profit": 2.12,
        }
    ]
    orch._last_kelly_size = 0.04
    orch._checkpoint_cycle_num = 0
    orch.tournament_config_path = tmp_path / "config" / "production.yaml"
    orch.tournament_config_path.parent.mkdir(parents=True, exist_ok=True)
    orch.settings = MagicMock()
    orch.settings.agent_mode = mode
    orch.settings.competition_dry_run = dry_run
    orch.trade_enforcer = MagicMock()
    orch.trade_enforcer.sync_from_portfolio = MagicMock()
    orch.confluence = MagicMock()
    orch.confluence.russian_doll = MagicMock()
    orch.confluence.russian_doll.check_drawdown = MagicMock(return_value=True)
    return orch


def test_save_and_load_roundtrip(tmp_path):
    ckpt = tmp_path / "agent_checkpoint.json"
    orch = _mock_orch(tmp_path)
    save_checkpoint(orch, cycle_num=3, path=ckpt)

    raw = json.loads(ckpt.read_text())
    assert raw["version"] == CHECKPOINT_VERSION
    assert raw["cycle_num"] == 3
    assert len(raw["open_positions"]) == 1
    assert raw["portfolio"]["trades_today"] == 2

    orch2 = _mock_orch(tmp_path)
    orch2.portfolio = PortfolioTracker()
    orch2._open_positions = []
    assert load_checkpoint(orch2, path=ckpt) is True
    assert len(orch2._open_positions) == 1
    assert orch2._open_positions[0]["token"] == "CAKE"
    assert orch2.portfolio.state.trades_today == 2
    assert orch2._checkpoint_cycle_num == 3
    orch2.trade_enforcer.sync_from_portfolio.assert_called_once_with(2)


def test_load_skips_mode_mismatch(tmp_path):
    ckpt = tmp_path / "agent_checkpoint.json"
    orch = _mock_orch(tmp_path, mode="paper")
    save_checkpoint(orch, cycle_num=1, path=ckpt)

    orch2 = _mock_orch(tmp_path, mode="competition")
    orch2._open_positions = []
    assert load_checkpoint(orch2, path=ckpt) is False
    assert orch2._open_positions == []


def test_load_missing_file(tmp_path):
    orch = _mock_orch(tmp_path)
    assert load_checkpoint(orch, path=tmp_path / "missing.json") is False

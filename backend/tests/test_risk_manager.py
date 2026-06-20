"""Unit tests for risk management."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.risk_manager import RISK_LAYERS, RiskManager
from strategies.signal_generation import TradeSignal


def test_drawdown_30_disqualifies():
    rm = RiskManager()
    can_trade, reason = rm.check_portfolio_risk(0.30, 0, 0)
    assert not can_trade
    assert rm.state.is_disqualified


def test_hard_halt_at_28():
    rm = RiskManager()
    can_trade, reason = rm.check_portfolio_risk(0.28, 0, 0)
    assert not can_trade
    assert rm.state.requires_liquidation
    assert "HARD HALT" in reason or "28%" in reason


def test_drawdown_20_halts():
    rm = RiskManager()
    can_trade, _ = rm.check_portfolio_risk(0.21, 0, 0)
    assert not can_trade
    assert rm.state.position_size_multiplier == 0.5


def test_daily_loss_halts():
    rm = RiskManager()
    can_trade, reason = rm.check_portfolio_risk(0.05, -0.11, 0)
    assert not can_trade
    assert "daily" in reason.lower()


def test_validate_trade_position_limit():
    rm = RiskManager()
    signal = TradeSignal(
        strategy="TEST",
        action="BUY",
        token="CAKE",
        position_size_pct=0.30,
        confidence=1.0,
        expected_return=0.05,
        risk=1.0,
    )
    valid, reason = rm.validate_trade(signal, 10000, 0, 0, True)
    assert not valid
    assert "25%" in reason or "limit" in reason.lower()


def test_consecutive_losses_halts():
    rm = RiskManager()
    can_trade, _ = rm.check_portfolio_risk(0.05, 0, 3)
    assert not can_trade


def test_anti_churn_blocks_reentry():
    rm = RiskManager()
    rm.record_exit("CAKE")
    can_enter, reason = rm.can_enter_position("CAKE")
    assert not can_enter
    assert "Anti-churn" in reason


def test_anti_churn_allows_after_cooldown():
    rm = RiskManager()
    rm._last_exit_times["CAKE"] = datetime.now(timezone.utc) - timedelta(hours=5)
    can_enter, reason = rm.can_enter_position("CAKE")
    assert can_enter


def test_tournament_sizing_healthy():
    rm = RiskManager()
    size = rm.calculate_tournament_position_size(confidence=0.8, drawdown_pct=0.05)
    assert 0.08 < size <= 0.15


def test_tournament_sizing_conservative_near_edge():
    rm = RiskManager()
    size_healthy = rm.calculate_tournament_position_size(0.8, 0.05)
    size_risky = rm.calculate_tournament_position_size(0.8, 0.22)
    assert size_risky < size_healthy


def test_risk_layers_defined():
    assert RISK_LAYERS["soft_halt"] == 0.20
    assert RISK_LAYERS["hard_halt"] == 0.28
    assert RISK_LAYERS["dq_line"] == 0.30

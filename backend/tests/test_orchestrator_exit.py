"""Tests for on-chain exit sells via orchestrator."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from agent.orchestrator import TradiOrchestrator
from data.twak_wrapper import SwapResult


def _make_orchestrator():
    with patch.object(TradiOrchestrator, "__init__", lambda self, **kw: None):
        orch = TradiOrchestrator.__new__(TradiOrchestrator)
    orch.settings = MagicMock(agent_mode="paper", competition_dry_run=False)
    orch.validator = MagicMock(is_eligible=lambda t: True)
    orch.cmc = AsyncMock()
    orch.cmc.get_24h_volatility = AsyncMock(return_value=0.02)
    orch.cmc.get_price = AsyncMock(return_value=100.0)
    orch.twak = AsyncMock()
    orch.bnb_sdk = AsyncMock()
    orch.bnb_sdk.log_trade_from_dict = AsyncMock(return_value=(True, "log"))
    orch.portfolio = MagicMock()
    orch.portfolio.position_market_value = MagicMock(return_value=500.0)
    orch.portfolio.close_position = MagicMock(return_value=(25.0, 0.05))
    orch.portfolio.state = MagicMock(cash_usd=10_500.0)
    orch.risk = MagicMock()
    orch._open_positions = []
    orch._trade_history = []
    orch._log_activity = MagicMock()
    return orch


def test_close_position_executes_sell_swap():
    orch = _make_orchestrator()
    orch.twak.execute_with_slippage_protection = AsyncMock(
        return_value=SwapResult(
            success=True,
            tx_hash="0xabc123",
            from_token="CAKE",
            to_token="USDT",
            from_amount=500,
            to_amount=498,
        )
    )
    pos = {
        "token_to": "CAKE",
        "entry_price": 95.0,
        "current_price": 100.0,
        "amount_usd": 500.0,
        "strategy": "STANDARD",
        "confidence": 0.8,
    }
    orch._open_positions = [pos]
    now = datetime.now(timezone.utc)

    async def run():
        return await orch._close_position(pos, "TAKE_PROFIT", now)

    ok = asyncio.run(run())
    assert ok is True
    orch.twak.execute_with_slippage_protection.assert_awaited_once_with("CAKE", "USDT", 500.0, 0.02)
    assert pos not in orch._open_positions
    assert orch._trade_history[0]["exit_tx_hash"] == "0xabc123"


def test_close_position_defers_when_swap_fails():
    orch = _make_orchestrator()
    orch.twak.execute_with_slippage_protection = AsyncMock(return_value="REJECTED_NO_QUOTE")
    pos = {
        "token_to": "ETH",
        "entry_price": 3000.0,
        "current_price": 2900.0,
        "amount_usd": 200.0,
        "strategy": "STANDARD",
    }
    orch._open_positions = [pos]
    now = datetime.now(timezone.utc)

    async def run():
        return await orch._close_position(pos, "STOP_LOSS", now)

    ok = asyncio.run(run())
    assert ok is False
    assert pos in orch._open_positions
    assert pos.get("exit_pending") == "STOP_LOSS"
    orch.portfolio.close_position.assert_not_called()

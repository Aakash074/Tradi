"""MIN_TRADE_USD gate on entry execution."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from agent.orchestrator import MIN_TRADE_USD, TradiOrchestrator
from strategies.signal_generation import TradeSignal


def _orch_for_execute():
    with patch.object(TradiOrchestrator, "__init__", lambda self, **kw: None):
        orch = TradiOrchestrator.__new__(TradiOrchestrator)
    orch.settings = MagicMock(agent_mode="competition", competition_dry_run=False)
    orch.validator = MagicMock(is_eligible=lambda t: True)
    orch.cmc = AsyncMock()
    orch.twak = AsyncMock()
    orch.portfolio = MagicMock()
    orch.portfolio.to_dict.return_value = {
        "total_value_usd": 50.0,
        "cash_usd": 50.0,
        "drawdown_pct": 0.0,
        "daily_pnl_pct": 0.0,
        "consecutive_losses": 0,
        "trades_today": 0,
    }
    orch.risk = MagicMock()
    orch.risk.check_portfolio_risk.return_value = (True, "ok")
    orch.risk.validate_trade.return_value = (True, "ok")
    orch.confluence = MagicMock()
    orch.confluence.russian_doll.state.max_positions = 4
    orch.confluence.stop_loss_pct = 0.015
    orch.confluence.take_profit_pct = 0.06
    orch._open_positions = []
    orch._trade_history = []
    orch._log_activity = MagicMock()
    orch._last_kelly_size = 0.0
    return orch


def test_execute_signal_skips_below_min_trade_usd():
    orch = _orch_for_execute()
    signal = TradeSignal(
        strategy="STANDARD",
        action="BUY",
        token="CAKE",
        position_size_pct=0.01,  # $0.50 on $50 wallet
    )

    async def run():
        return await orch.execute_signal(signal)

    result = asyncio.run(run())
    assert result is None
    orch.twak.execute_with_slippage_protection.assert_not_called()
    orch._log_activity.assert_called()
    assert "MIN_TRADE_USD" in orch._log_activity.call_args[0][3]


def test_execute_signal_allows_at_min_trade_usd():
    orch = _orch_for_execute()
    orch.cmc.get_24h_volatility = AsyncMock(return_value=0.02)
    orch.cmc.get_price = AsyncMock(return_value=2.5)
    orch.cmc.get_ohlcv = AsyncMock(return_value={"close": [2.5], "high": [2.5], "low": [2.5]})
    orch.portfolio.allocate_cash = MagicMock(return_value=True)
    orch.portfolio.record_entry = MagicMock()
    orch.portfolio.mark_to_market = MagicMock()
    orch.portfolio.state.cash_usd = 47.5
    orch.trade_enforcer = MagicMock()
    orch.trade_enforcer.mark_trade_executed = MagicMock()
    from data.twak_wrapper import SwapResult

    orch.twak.execute_with_slippage_protection = AsyncMock(
        return_value=SwapResult(
            success=True,
            tx_hash="0xtest",
            from_token="USDT",
            to_token="CAKE",
            from_amount=2.5,
            to_amount=2.5,
        )
    )
    signal = TradeSignal(
        strategy="QUALIFICATION",
        action="BUY",
        token="CAKE",
        position_size_pct=0.05,  # $2.50 on $50 wallet
    )

    async def run():
        return await orch.execute_signal(signal)

    result = asyncio.run(run())
    assert result is not None
    orch.twak.execute_with_slippage_protection.assert_awaited_once()
    assert orch.twak.execute_with_slippage_protection.await_args[0][2] >= MIN_TRADE_USD

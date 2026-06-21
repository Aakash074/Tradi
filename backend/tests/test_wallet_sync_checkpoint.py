"""Wallet sync runs after checkpoint restore (positions + balances)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.orchestrator import TradiOrchestrator
from agent.portfolio import PortfolioTracker


def _orch_stub(dry_run: bool = True):
    orch = TradiOrchestrator.__new__(TradiOrchestrator)
    orch.settings = MagicMock(agent_mode="competition", competition_dry_run=dry_run)
    orch.portfolio = PortfolioTracker(10_000.0)
    orch._open_positions = []
    orch.twak = MagicMock()
    orch.cmc = MagicMock()
    return orch


@pytest.mark.parametrize("after_checkpoint", [False, True])
def test_sync_seeds_wallet_when_no_open_positions(after_checkpoint):
    orch = _orch_stub()
    orch.twak.get_wallet_balance_usd = AsyncMock(return_value=6.42)

    asyncio.run(orch._sync_portfolio_from_wallet(after_checkpoint=after_checkpoint))

    assert orch.portfolio.state.wallet_synced is True
    assert orch.portfolio.state.cash_usd == pytest.approx(6.42)
    assert orch.portfolio.state.total_value_usd == pytest.approx(6.42)


def test_sync_after_checkpoint_replaces_paper_seed():
    orch = _orch_stub()
    orch.portfolio.load_state_dict({"cash_usd": 10_000.0, "total_value_usd": 10_000.0})
    orch.twak.get_wallet_balance_usd = AsyncMock(return_value=6.42)

    asyncio.run(orch._sync_portfolio_from_wallet(after_checkpoint=True))

    assert orch.portfolio.state.cash_usd == pytest.approx(6.42)
    assert orch.portfolio.state.initial_value_usd == pytest.approx(6.42)


def test_sync_deferred_when_dry_run_has_paper_positions():
    orch = _orch_stub(dry_run=True)
    orch._open_positions = [{"token": "CAKE", "amount_usd": 500.0, "entry_price": 2.0, "current_price": 2.0}]
    orch.portfolio.state.cash_usd = 9_500.0
    orch.twak.get_wallet_balance_usd = AsyncMock(return_value=6.42)

    asyncio.run(orch._sync_portfolio_from_wallet(after_checkpoint=True))

    assert orch.portfolio.state.cash_usd == pytest.approx(9_500.0)


def test_sync_reconciles_live_checkpoint_with_positions():
    orch = _orch_stub(dry_run=False)
    orch._open_positions = [
        {"token": "CAKE", "amount_usd": 20.0, "entry_price": 2.0, "current_price": 2.0}
    ]
    orch.twak.get_wallet_balance_usd = AsyncMock(return_value=50.0)

    asyncio.run(orch._sync_portfolio_from_wallet(after_checkpoint=True))

    assert orch.portfolio.state.wallet_synced is True
    assert orch.portfolio.state.cash_usd == pytest.approx(30.0)
    assert orch.portfolio.state.positions_value_usd == pytest.approx(20.0)

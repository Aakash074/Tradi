"""Unit tests for portfolio valuation and PnL."""

from agent.portfolio import PortfolioTracker


def test_open_close_realized_pnl():
    p = PortfolioTracker(initial_value=10_000.0)
    assert p.allocate_cash(1_000.0, "CAKE")

    pnl_usd, pnl_pct = p.close_position(1_000.0, entry_price=100.0, exit_price=104.5, token="CAKE")
    assert pnl_usd == 45.0
    assert pnl_pct == 0.045
    assert p.state.cash_usd == 10_045.0
    assert p.state.realized_pnl_usd == 45.0


def test_mark_to_market_includes_unrealized():
    p = PortfolioTracker(initial_value=10_000.0)
    p.allocate_cash(2_000.0, "ETH")

    positions = [
        {
            "amount_usd": 2_000.0,
            "entry_price": 100.0,
            "current_price": 103.0,
        }
    ]
    p.mark_to_market(positions)

    assert p.state.positions_value_usd == 2_060.0
    assert p.state.cash_usd == 8_000.0
    assert p.state.total_value_usd == 10_060.0
    assert p.state.unrealized_pnl_usd == 60.0
    assert p.state.total_return_pct == 0.006


def test_seed_from_wallet_replaces_paper_capital():
    p = PortfolioTracker(initial_value=10_000.0)
    p.seed_from_wallet(3_500.0)

    assert p.state.cash_usd == 3_500.0
    assert p.state.initial_value_usd == 3_500.0
    assert p.state.wallet_synced is True


def test_profit_protection_trim_returns_cash():
    p = PortfolioTracker(initial_value=10_000.0)
    p.allocate_cash(2_000.0, "CAKE")

    pnl = p.trim_position(500.0, entry_price=10.0, exit_price=12.0, token="CAKE")
    assert pnl == 100.0
    assert p.state.cash_usd == 8_600.0

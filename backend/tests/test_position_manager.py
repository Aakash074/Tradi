"""Unit tests for profit protection scaling."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.position_manager import apply_profit_protection_scaling


def test_profit_protection_trims_at_10_pct_gain():
    positions = [{
        "token_to": "CAKE",
        "entry_price": 100,
        "current_price": 112,
        "amount_usd": 2000,
    }]
    actions = apply_profit_protection_scaling(positions, portfolio_value=10000)
    assert len(actions) == 1
    assert positions[0]["amount_usd"] == 1500  # 15% of 10000


def test_profit_protection_trims_at_20_pct_gain():
    positions = [{
        "token_to": "ETH",
        "entry_price": 100,
        "current_price": 125,
        "amount_usd": 2000,
    }]
    actions = apply_profit_protection_scaling(positions, portfolio_value=10000)
    assert len(actions) == 1
    assert positions[0]["amount_usd"] == 1000  # 10% of 10000


def test_profit_protection_no_action_below_threshold():
    positions = [{
        "token_to": "DOGE",
        "entry_price": 100,
        "current_price": 105,
        "amount_usd": 1000,
    }]
    actions = apply_profit_protection_scaling(positions, portfolio_value=10000)
    assert len(actions) == 0
    assert positions[0]["amount_usd"] == 1000

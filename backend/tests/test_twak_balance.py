"""Tests for TWAK wallet balance parsing."""

import asyncio

import pytest

from data.twak_wrapper import TWAKWrapper


def test_parse_balance_to_usd_stable_and_priced_tokens():
    twak = TWAKWrapper()

    async def price_fn(sym: str) -> float:
        return {"BNB": 600.0, "CAKE": 2.5}.get(sym, 1.0)

    output = """
    BNB: 0.5
    1000 USDT
    CAKE = 200
    """

    async def run():
        return await twak._parse_balance_to_usd(output, price_fn)

    total = asyncio.run(run())
    assert total == pytest.approx(0.5 * 600 + 1000 + 200 * 2.5)

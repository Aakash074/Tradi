"""Tests for TWAK wallet balance parsing."""

import asyncio

import pytest

from data.twak_wrapper import TWAKWrapper


def test_parse_balance_json_bsc():
    twak = TWAKWrapper()
    output = """
    {
      "chain": "bsc",
      "symbol": "BNB",
      "available": "0.0099950868",
      "totalUsd": 5.88
    }
    """
    assert twak._parse_balance_json(output) == pytest.approx(5.88)


def test_parse_balance_json_all_chains():
    twak = TWAKWrapper()
    output = """[
      {"chain": "bsc", "symbol": "BNB", "totalUsd": 5.88, "tokens": []}
    ]"""
    assert twak._parse_balance_json(output) == pytest.approx(5.88)


def test_fetch_wallet_balance_prefers_bsc(monkeypatch):
    twak = TWAKWrapper()
    calls: list[list[str]] = []

    def fake_run(args):
        calls.append(args)
        if "bsc" in args:
            return True, '{"chain":"bsc","totalUsd":5.88}'
        return False, "fail"

    monkeypatch.setattr(twak, "_run_twak", fake_run)
    ok, out = twak._fetch_wallet_balance_output()
    assert ok is True
    assert "5.88" in out
    assert "bsc" in calls[0]


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

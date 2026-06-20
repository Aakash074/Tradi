"""Tests for CMC MCP client response parsing."""

import asyncio

import pytest

from data.cmc_mcp_client import CMCMCPClient


def test_extract_fear_greed_nested():
    data = {"data": {"fear_greed_index": 18, "quote": {"USD": {"price": 1}}}}
    assert CMCMCPClient._extract_fear_greed(data) == 18


def test_extract_fear_greed_object_value():
    data = {"data": {"fear_greed_index": {"value": 72, "classification": "Greed"}}}
    assert CMCMCPClient._extract_fear_greed(data) == 72


def test_extract_funding_rate_from_list():
    data = {
        "data": [
            {"symbol": "BTC", "funding_rate": 0.012},
            {"symbol": "ETH", "funding_rate": -0.004},
        ]
    }
    assert CMCMCPClient._extract_funding_rate(data, "ETH") == pytest.approx(-0.004)


def test_normalize_ta_bullish_signal():
    raw = {"data": {"signal": "STRONG_BUY", "score": 82}}
    ta = CMCMCPClient._normalize_ta(raw, "CAKE", "1h")
    assert ta["bias"] == "BULLISH"
    assert ta["score"] == pytest.approx(0.82)


def test_get_fear_and_greed_mock_when_not_live():
    client = CMCMCPClient(enabled=True, live_cmc=False)

    async def run():
        return await client.get_fear_and_greed()

    result = asyncio.run(run())
    assert "value" in result
    assert result["source"] in ("mock", "mock_fallback")

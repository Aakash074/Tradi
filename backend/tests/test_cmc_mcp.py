"""Tests for CMC MCP client response parsing."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

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


def test_fear_greed_alternative_me():
    client = CMCMCPClient(enabled=True, live_cmc=True)
    mock_resp = MagicMock()
    mock_resp.raise_for_status = lambda: None
    mock_resp.json = lambda: {
        "data": [{"value": "23", "value_classification": "Extreme Fear"}],
    }

    async def run():
        with patch("data.cmc_mcp_client.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
            with patch.object(client, "_use_live_api", return_value=True):
                with patch.object(client, "_request", AsyncMock(return_value={})):
                    with patch.object(client, "_fear_greed_via_pro_api", AsyncMock(return_value=None)):
                        return await client.get_fear_and_greed()

    result = asyncio.run(run())
    assert result["value"] == 23
    assert result["source"] == "alternative.me"
    assert result["classification"] == "Extreme Fear"

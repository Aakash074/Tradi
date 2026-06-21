"""Tests for live OHLCV provider (CMC + Binance fallback)."""

import asyncio
from unittest.mock import AsyncMock, patch

from data.ohlcv_provider import (
    binance_symbol,
    fetch_binance_ohlcv,
    fetch_live_ohlcv,
    parse_binance_klines,
    parse_cmc_ohlcv,
)


def test_binance_symbol_skips_stables():
    assert binance_symbol("USDT") is None
    assert binance_symbol("CAKE") == "CAKEUSDT"


def test_parse_binance_klines():
    rows = [
        [0, "1.0", "1.1", "0.9", "1.05", "1000", 0, 0, 0, 0, 0, 0],
        [1, "1.05", "1.2", "1.0", "1.15", "2000", 0, 0, 0, 0, 0, 0],
    ]
    out = parse_binance_klines(rows)
    assert out is not None
    assert out["close"] == [1.05, 1.15]
    assert out["volume"] == [1000.0, 2000.0]


def test_parse_cmc_ohlcv():
    payload = {
        "status": {"error_code": 0},
        "data": {
            "CAKE": [
                {
                    "quotes": [
                        {"quote": {"USD": {"open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05, "volume": 500}}},
                        {"quote": {"USD": {"open": 1.05, "high": 1.2, "low": 1.0, "close": 1.15, "volume": 600}}},
                    ]
                }
            ]
        },
    }
    out = parse_cmc_ohlcv(payload, "CAKE")
    assert out is not None
    assert len(out["close"]) == 2


def test_fetch_live_ohlcv_uses_binance_when_cmc_unavailable():
    async def run():
        with patch("data.ohlcv_provider.fetch_cmc_ohlcv", AsyncMock(return_value=None)):
            with patch(
                "data.ohlcv_provider.fetch_binance_ohlcv",
                AsyncMock(
                    return_value={
                        "open": [1.0],
                        "high": [1.1],
                        "low": [0.9],
                        "close": [1.05],
                        "volume": [100.0],
                    }
                ),
            ):
                ohlcv, source = await fetch_live_ohlcv("CAKE", "1h", 50, cmc_api_key="test-key")
                assert source == "binance"
                assert ohlcv["close"] == [1.05]

    asyncio.run(run())

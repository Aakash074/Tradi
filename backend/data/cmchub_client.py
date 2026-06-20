"""CoinMarketCap AI Agent Hub client with x402 micropayment support."""

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from config import get_settings
from data.cache import DataCache

logger = logging.getLogger(__name__)


class CMCHubClient:
    """Fetches market data from CMC Agent Hub. Falls back to mock data in paper mode."""

    BASE_URL = "https://pro-api.coinmarketcap.com/v1"

    def __init__(self, cache: Optional[DataCache] = None):
        self.settings = get_settings()
        self.cache = cache or DataCache()
        self.x402_payments_count = 0
        self.x402_total_cost_usd = 0.0

    async def _request(self, endpoint: str, params: dict) -> dict:
        cache_key = f"cmc:{endpoint}:{':'.join(f'{k}={v}' for k, v in sorted(params.items()))}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        if self.settings.agent_mode == "paper" or not self.settings.cmc_api_key:
            return self._mock_response(endpoint, params)

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.BASE_URL}/{endpoint}",
                params=params,
                headers={"X-CMC_PRO_API_KEY": self.settings.cmc_api_key},
            )
            resp.raise_for_status()
            data = resp.json()
            self.cache.set(cache_key, data)
            return data

    async def x402_request(self, endpoint: str, max_payment: float = 0.01) -> dict:
        """Simulate x402 micropayment for premium data."""
        self.x402_payments_count += 1
        cost = min(max_payment, 0.005 + random.random() * 0.005)
        self.x402_total_cost_usd += cost
        logger.info("x402 payment: $%.4f for %s", cost, endpoint)
        return await self._request(endpoint.replace("x402/", ""), {})

    def _mock_response(self, endpoint: str, params: dict) -> dict:
        symbol = params.get("symbol", "CAKE")
        base_price = {"CAKE": 2.45, "ETH": 3500, "DOGE": 0.12, "BNB": 650}.get(
            symbol.split(",")[0], 1.0
        )
        noise = random.uniform(-0.02, 0.02)
        price = base_price * (1 + noise)
        return {
            "data": {
                symbol: {
                    "quote": {"USD": {"price": price, "volume_24h": 5_000_000, "percent_change_24h": noise * 100}},
                }
            }
        }

    async def get_price(self, symbol: str) -> float:
        data = await self._request("cryptocurrency/quotes/latest", {"symbol": symbol})
        return float(data["data"][symbol]["quote"]["USD"]["price"])

    async def get_prices(self, symbols: list[str]) -> dict[str, float]:
        result = {}
        for sym in symbols:
            try:
                result[sym] = await self.get_price(sym)
            except Exception as e:
                logger.warning("Failed to fetch price for %s: %s", sym, e)
        return result

    async def get_ohlcv(self, symbol: str, interval: str = "1h", limit: int = 100) -> dict[str, list[float]]:
        cache_key = f"ohlcv:{symbol}:{interval}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        if self.settings.agent_mode == "paper" or not self.settings.cmc_api_key:
            ohlcv = self._generate_mock_ohlcv(symbol, limit)
            self.cache.set(cache_key, ohlcv, ttl_seconds=60)
            return ohlcv

        # Real API would fetch OHLCV here
        ohlcv = self._generate_mock_ohlcv(symbol, limit)
        self.cache.set(cache_key, ohlcv, ttl_seconds=60)
        return ohlcv

    def _generate_mock_ohlcv(self, symbol: str, limit: int) -> dict[str, list[float]]:
        base = {"CAKE": 2.45, "ETH": 3500, "DOGE": 0.12, "BNB": 650}.get(symbol, 1.0)
        close, high, low, open_, volume = [], [], [], [], []
        price = base
        for _ in range(limit):
            change = random.uniform(-0.03, 0.03)
            o = price
            c = price * (1 + change)
            h = max(o, c) * (1 + random.uniform(0, 0.01))
            l = min(o, c) * (1 - random.uniform(0, 0.01))
            v = random.uniform(100_000, 2_000_000)
            open_.append(o)
            close.append(c)
            high.append(h)
            low.append(l)
            volume.append(v)
            price = c
        return {"open": open_, "high": high, "low": low, "close": close, "volume": volume}

    async def get_fear_greed_index(self) -> dict:
        cached = self.cache.get("sentiment:fear_greed")
        if cached:
            return cached
        result = {"value": random.randint(25, 75), "classification": "Neutral"}
        self.cache.set("sentiment:fear_greed", result)
        return result

    def get_x402_stats(self) -> dict:
        return {
            "payments_count": self.x402_payments_count,
            "total_cost_usd": round(self.x402_total_cost_usd, 4),
        }

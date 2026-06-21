"""CoinMarketCap AI Agent Hub client with x402 micropayment support."""

import asyncio
import logging
import os
import random
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from config import get_settings
from data.cache import DataCache
from data.cmc_mcp_client import CMCMCPClient
from data.ohlcv_provider import fetch_live_ohlcv
from data.twak_wrapper import TWAKWrapper

logger = logging.getLogger(__name__)


class CMCHubClient:
    """Fetches market data from CMC Agent Hub. Falls back to mock data in paper mode."""

    BASE_URL = "https://pro-api.coinmarketcap.com/v1"

    def __init__(self, cache: Optional[DataCache] = None, live_cmc: bool = False):
        self.settings = get_settings()
        self.live_cmc = live_cmc or os.environ.get("LIVE_CMC", "").lower() in ("1", "true", "yes")
        self.cache = cache or DataCache()
        self.twak = TWAKWrapper()
        self.mcp = CMCMCPClient(
            cache=self.cache,
            live_cmc=self.live_cmc,
            twak_x402_fn=self.twak.x402_fetch_url,
        )
        self.x402_payments_count = 0
        self.x402_total_cost_usd = 0.0
        self._ohlcv_source_counts: dict[str, int] = {"cmc": 0, "binance": 0, "mock": 0}

    def _use_live_ohlcv(self) -> bool:
        """Live candles when --live-cmc or competition/live mode."""
        return self.live_cmc or self.settings.agent_mode in ("competition", "live")

    async def get_ohlcv(self, symbol: str, interval: str = "1h", limit: int = 100) -> dict[str, list[float]]:
        cache_key = f"ohlcv:{symbol}:{interval}:{limit}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        if not self._use_live_ohlcv():
            ohlcv = self._generate_mock_ohlcv(symbol, limit)
            self._ohlcv_source_counts["mock"] += 1
            self.cache.set(cache_key, ohlcv, ttl_seconds=60)
            return ohlcv

        live, source = await fetch_live_ohlcv(
            symbol, interval, limit, cmc_api_key=self.settings.cmc_api_key
        )
        if live:
            self._ohlcv_source_counts[source] = self._ohlcv_source_counts.get(source, 0) + 1
            ttl = 300 if interval in ("1h", "4h", "1d") else 90
            self.cache.set(cache_key, live, ttl_seconds=ttl)
            if self._ohlcv_source_counts.get(source, 0) == 1:
                logger.info(
                    "Live OHLCV active for %s — primary source: %s (interval=%s)",
                    symbol,
                    source,
                    interval,
                )
            return live

        logger.warning(
            "Live OHLCV unavailable for %s (%s) — using mock candles",
            symbol,
            interval,
        )
        ohlcv = self._generate_mock_ohlcv(symbol, limit)
        self._ohlcv_source_counts["mock"] += 1
        self.cache.set(cache_key, ohlcv, ttl_seconds=60)
        return ohlcv

    def get_ohlcv_stats(self) -> dict:
        return dict(self._ohlcv_source_counts)

    async def _request(self, endpoint: str, params: dict) -> dict:
        cache_key = f"cmc:{endpoint}:{':'.join(f'{k}={v}' for k, v in sorted(params.items()))}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        if (self.settings.agent_mode == "paper" and not self.live_cmc) or not self.settings.cmc_api_key:
            if self.live_cmc and not self.settings.cmc_api_key:
                logger.warning("live-cmc requested but CMC_API_KEY missing — using mock data")
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
        """Pay for premium CMC x402 endpoint via TWAK wallet."""
        from data.x402_payment import X402Payment

        payer = X402Payment(
            max_amount_usdc=max_payment,
            enabled=True,
            paper_mode=self.settings.agent_mode == "paper" and not self.settings.competition_dry_run,
            twak_request=self.twak.x402_fetch_url,
        )
        data = await payer.pay_for_data(endpoint, max_amount_usdc=max_payment)
        if data:
            stats = payer.get_stats()
            self.x402_payments_count += stats["payments_count"]
            self.x402_total_cost_usd += stats["total_cost_usd"]
            return data
        return {}

    def _mock_response(self, endpoint: str, params: dict) -> dict:
        symbol = params.get("symbol", "CAKE")
        if isinstance(symbol, str) and "," in symbol:
            symbol = symbol.split(",")[0]
        base_price = {"CAKE": 2.45, "ETH": 3500, "DOGE": 0.12, "BNB": 650, "TON": 5.0}.get(
            symbol.upper() if isinstance(symbol, str) else "CAKE", 1.0
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

    @staticmethod
    def _lookup_quote_node(payload: dict, symbol: str) -> Optional[dict]:
        """Resolve CMC quote node — keys may differ in casing (e.g. TON → Ton)."""
        data = payload.get("data")
        if not data or not isinstance(data, dict):
            return None

        if symbol in data:
            return data[symbol]

        upper = symbol.upper()
        for key, node in data.items():
            if isinstance(key, str) and key.upper() == upper and isinstance(node, dict):
                return node

        for node in data.values():
            if not isinstance(node, dict):
                continue
            sym = node.get("symbol")
            if isinstance(sym, str) and sym.upper() == upper:
                return node

        return None

    @staticmethod
    def _parse_quote_price(payload: dict, symbol: str) -> Optional[float]:
        node = CMCHubClient._lookup_quote_node(payload, symbol)
        if not node:
            return None
        try:
            return float(node["quote"]["USD"]["price"])
        except (KeyError, TypeError, ValueError):
            return None

    async def get_price(self, symbol: str) -> float:
        data = await self._request("cryptocurrency/quotes/latest", {"symbol": symbol})
        price = self._parse_quote_price(data, symbol)
        if price is not None:
            return price

        keys: list[Any] = []
        if isinstance(data.get("data"), dict):
            keys = list(data["data"].keys())
        logger.warning(
            "CMC quote shape mismatch for %s (data keys=%s) — using fallback price",
            symbol,
            keys,
        )
        mock = self._mock_response("cryptocurrency/quotes/latest", {"symbol": symbol})
        return self._parse_quote_price(mock, symbol) or 1.0

    async def get_prices(self, symbols: list[str]) -> dict[str, float]:
        result = {}
        for sym in symbols:
            try:
                result[sym] = await self.get_price(sym)
            except Exception as e:
                logger.warning("Failed to fetch price for %s: %s", sym, e)
        return result

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
        return await self.mcp.get_fear_and_greed()

    async def get_funding_rate_8h(self, symbol: str) -> float:
        data = await self.mcp.get_funding_rates(symbol)
        return float(data.get("funding_rate", 0.0))

    async def get_technical_analysis(self, symbol: str, interval: str = "1h") -> dict:
        return await self.mcp.get_technical_analysis(symbol, interval=interval)

    async def get_24h_volatility(self, symbol: str = "CAKE") -> float:
        ohlcv = await self.get_ohlcv(symbol, limit=24)
        close = ohlcv["close"]
        if len(close) < 2:
            return 0.02
        returns = [(close[i] - close[i - 1]) / close[i - 1] for i in range(1, len(close))]
        import statistics
        return statistics.stdev(returns) if len(returns) > 1 else 0.02

    async def get_30d_volatility(self, symbol: str = "CAKE") -> float:
        ohlcv = await self.get_ohlcv(symbol, limit=100)
        close = ohlcv["close"]
        if len(close) < 2:
            return 0.02
        returns = [(close[i] - close[i - 1]) / close[i - 1] for i in range(1, len(close))]
        import statistics
        return statistics.stdev(returns) if len(returns) > 1 else 0.02

    async def get_exchange_flows_24h(self, symbol: str) -> tuple[float, float]:
        cache_key = f"flows:{symbol}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached["inflow"], cached["outflow"]
        inflow = random.uniform(1_000_000, 10_000_000)
        outflow = random.uniform(1_000_000, 10_000_000)
        self.cache.set(cache_key, {"inflow": inflow, "outflow": outflow}, ttl_seconds=900)
        return inflow, outflow

    async def get_order_book(self, symbol: str, depth: int = 10) -> tuple[list[dict], list[dict]]:
        cache_key = f"book:{symbol}:{depth}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached["bids"], cached["asks"]
        price = await self.get_price(symbol)
        bids = [{"price": price * (1 - 0.001 * i), "size": random.uniform(1000, 50000)} for i in range(depth)]
        asks = [{"price": price * (1 + 0.001 * i), "size": random.uniform(1000, 50000)} for i in range(depth)]
        # Slight random imbalance
        if random.random() > 0.5:
            for b in bids:
                b["size"] *= 1.3
        self.cache.set(cache_key, {"bids": bids, "asks": asks}, ttl_seconds=30)
        return bids, asks

    async def get_microstructure_heatmap(self, tokens: list[str]) -> list[dict]:
        """Momentum + mock funding/flow data for dashboard heatmap."""
        result = []
        for token in tokens[:30]:
            funding = await self.get_funding_rate_8h(token)
            inflow, outflow = await self.get_exchange_flows_24h(token)
            ratio = outflow / (inflow + 1e-9)
            if funding < -0.01:
                fund_sig = "BULLISH_EDGE"
            elif funding > 0.015:
                fund_sig = "BEARISH_EDGE"
            else:
                fund_sig = "NEUTRAL"
            if ratio > 2.0:
                flow_sig = "ACCUMULATION"
            elif ratio < 0.5:
                flow_sig = "DISTRIBUTION"
            else:
                flow_sig = "NEUTRAL"
            ohlcv = await self.get_ohlcv(token, limit=20)
            close = ohlcv.get("close", [])
            book_imb = 0.0
            if len(close) >= 2:
                book_imb = (close[-1] - close[-2]) / close[-2]
            result.append({
                "token": token,
                "funding_rate": round(funding, 6),
                "funding_signal": fund_sig,
                "inflow_usd": round(inflow, 0),
                "outflow_usd": round(outflow, 0),
                "flow_signal": flow_sig,
                "book_imbalance": round(book_imb, 3),
            })
        return result

    def get_x402_stats(self) -> dict:
        mcp_stats = self.mcp.get_x402_stats()
        return {
            "payments_count": self.x402_payments_count + mcp_stats.get("payments_count", 0),
            "total_cost_usd": round(
                self.x402_total_cost_usd + mcp_stats.get("total_cost_usd", 0), 4
            ),
            "enabled": mcp_stats.get("enabled", False),
            "failures": mcp_stats.get("failures", 0),
            "max_payment_usdc": mcp_stats.get("max_payment_usdc", 0.01),
        }

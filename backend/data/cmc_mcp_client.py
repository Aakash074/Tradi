"""CoinMarketCap Agent Hub MCP client — Fear & Greed, derivatives, technicals."""

import logging
import os
import random
from typing import Any, Optional

import httpx

from config import get_settings
from data.cache import DataCache
from data.x402_payment import X402Payment

logger = logging.getLogger(__name__)

FNG_CLASSIFICATIONS = (
    (75, "Extreme Greed"),
    (55, "Greed"),
    (45, "Neutral"),
    (25, "Fear"),
    (0, "Extreme Fear"),
)

PRO_API_BASE = "https://pro-api.coinmarketcap.com/v1"


class CMCMCPClient:
    """
    CMC Agent Hub MCP — Fear & Greed, derivatives funding, technical analysis.

    Premium `/x402/v1/*` endpoints accept x402 USDC micropayments (via TWAK).
    Standard `/v1/*` fallbacks use CMC_API_KEY when x402 is disabled or fails.
    """

    BASE_URL = "https://pro-api.coinmarketcap.com/x402/v1"

    def __init__(
        self,
        cache: Optional[DataCache] = None,
        live_cmc: bool = False,
        enabled: Optional[bool] = None,
        x402: Optional[X402Payment] = None,
        twak_x402_fn=None,
    ):
        self.settings = get_settings()
        self.cache = cache or DataCache()
        self.live_cmc = live_cmc or os.environ.get("LIVE_CMC", "").lower() in ("1", "true", "yes")
        self.api_key = self.settings.cmc_mcp_api_key or self.settings.cmc_api_key
        self.enabled = enabled if enabled is not None else bool(self.api_key or self.settings.x402_enabled)

        paper = self.settings.agent_mode == "paper" and not self.settings.competition_dry_run
        self.x402 = x402 or X402Payment(
            max_amount_usdc=self.settings.x402_max_payment_usdc,
            enabled=self.settings.x402_enabled,
            paper_mode=paper,
            twak_request=twak_x402_fn,
        )

    def _use_live_api(self) -> bool:
        if self.live_cmc:
            return True
        if self.settings.x402_enabled:
            return True
        if self.api_key and self.settings.agent_mode in ("competition", "live"):
            return True
        return bool(self.api_key and self.live_cmc)

    async def _request_pro_v1(self, path: str, params: Optional[dict] = None) -> dict:
        """Standard Pro API (included in CMC plan)."""
        if not self.api_key:
            return {}
        params = params or {}
        url = f"{PRO_API_BASE}/{path.lstrip('/')}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                url,
                params=params,
                headers={"X-CMC_PRO_API_KEY": self.api_key},
            )
            resp.raise_for_status()
            return resp.json()

    async def _request(self, path: str, params: Optional[dict] = None) -> dict:
        params = params or {}
        cache_key = f"mcp:{path}:{':'.join(f'{k}={v}' for k, v in sorted(params.items()))}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        if not self._use_live_api():
            return {}

        url = f"{self.BASE_URL}/{path.lstrip('/')}"

        # x402 micropayment path (no API key on x402 endpoints)
        if self.x402.enabled:
            data = await self.x402.pay_for_data(url, params)
            if data:
                self.cache.set(cache_key, data, ttl_seconds=900)
                return data

        # Legacy attempt with Pro API key (most x402 paths still return 402)
        if self.api_key:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(
                        url,
                        params=params,
                        headers={"X-CMC_PRO_API_KEY": self.api_key},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        self.cache.set(cache_key, data, ttl_seconds=900)
                        return data
            except httpx.HTTPStatusError as e:
                if e.response.status_code != 402:
                    raise

        return {}

    @staticmethod
    def _fng_classification(value: int) -> str:
        for threshold, label in FNG_CLASSIFICATIONS:
            if value >= threshold:
                return label
        return "Extreme Fear"

    @staticmethod
    def _extract_fear_greed(data: dict) -> Optional[int]:
        """Parse Fear & Greed from varied MCP / CMC response shapes."""
        if not data:
            return None

        candidates: list[Any] = []

        root = data.get("data", data)
        if isinstance(root, dict):
            for key in ("fear_greed_index", "fear_and_greed", "fear_greed", "value"):
                if key in root:
                    candidates.append(root[key])
            quote = root.get("quote", {})
            if isinstance(quote, dict):
                for key in ("fear_greed_index", "fear_and_greed"):
                    if key in quote:
                        candidates.append(quote[key])
        elif isinstance(root, list) and root:
            first = root[0]
            if isinstance(first, dict):
                for key in ("fear_greed_index", "value"):
                    if key in first:
                        candidates.append(first[key])

        for item in candidates:
            if isinstance(item, dict):
                val = item.get("value") or item.get("score")
                if val is not None:
                    return int(val)
            if isinstance(item, (int, float)):
                return int(item)
            if isinstance(item, str) and item.isdigit():
                return int(item)
        return None

    async def _fear_greed_via_pro_api(self) -> Optional[dict]:
        """Free-tier Pro API fallback for Fear & Greed."""
        try:
            data = await self._request_pro_v1("fear-greed/latest")
            value = self._extract_fear_greed(data)
            if value is None and isinstance(data.get("data"), list) and data["data"]:
                latest = data["data"][0]
                value = int(latest.get("value", 0))
            if value is not None:
                return {
                    "value": value,
                    "classification": self._fng_classification(value),
                    "source": "pro_api",
                }
        except Exception as e:
            logger.debug("Pro API fear/greed fallback failed: %s", e)
        return None

    async def get_fear_and_greed(self) -> dict:
        """Global Fear & Greed index."""
        cache_key = "sentiment:fear_greed_mcp"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        if not self._use_live_api():
            result = {"value": random.randint(25, 75), "classification": "Neutral", "source": "mock"}
            self.cache.set(cache_key, result, ttl_seconds=900)
            return result

        try:
            data = await self._request("global-metrics/quotes/latest")
            value = self._extract_fear_greed(data)
            if value is not None:
                result = {
                    "value": value,
                    "classification": self._fng_classification(value),
                    "source": "x402" if self.x402.enabled else "mcp",
                }
                self.cache.set(cache_key, result, ttl_seconds=900)
                return result
        except Exception as e:
            logger.warning("MCP fear/greed unavailable: %s", e)

        pro = await self._fear_greed_via_pro_api()
        if pro:
            self.cache.set(cache_key, pro, ttl_seconds=900)
            return pro

        result = {"value": random.randint(25, 75), "classification": "Neutral", "source": "mock_fallback"}
        self.cache.set(cache_key, result, ttl_seconds=300)
        return result

    @staticmethod
    def _extract_funding_rate(data: dict, symbol: str) -> Optional[float]:
        if not data:
            return None

        sym = symbol.upper()
        root = data.get("data", data)

        def _scan(node: Any) -> Optional[float]:
            if isinstance(node, dict):
                node_sym = str(node.get("symbol", node.get("name", ""))).upper()
                for key in ("funding_rate", "fundingRate", "rate", "last_funding_rate"):
                    if key in node and (not node_sym or node_sym == sym or sym in node_sym):
                        try:
                            return float(node[key])
                        except (TypeError, ValueError):
                            continue
                for child in node.values():
                    found = _scan(child)
                    if found is not None:
                        return found
            elif isinstance(node, list):
                for item in node:
                    found = _scan(item)
                    if found is not None:
                        return found
            return None

        return _scan(root)

    async def get_funding_rates(self, symbol: str) -> dict:
        """Perpetual funding rates for a symbol."""
        cache_key = f"mcp:funding:{symbol.upper()}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        if not self._use_live_api():
            rate = random.uniform(-0.02, 0.02)
            result = {"symbol": symbol.upper(), "funding_rate": rate, "source": "mock"}
            self.cache.set(cache_key, result, ttl_seconds=3600)
            return result

        try:
            raw = await self._request("derivatives/exchanges/quotes", {"symbol": symbol.upper()})
            rate = self._extract_funding_rate(raw, symbol)
            if rate is not None:
                source = "x402" if self.x402.enabled else "mcp"
                result = {"symbol": symbol.upper(), "funding_rate": rate, "source": source}
                self.cache.set(cache_key, result, ttl_seconds=3600)
                return result
        except Exception as e:
            logger.warning("MCP funding rates failed for %s: %s", symbol, e)

        rate = random.uniform(-0.02, 0.02)
        result = {"symbol": symbol.upper(), "funding_rate": rate, "source": "mock_fallback"}
        self.cache.set(cache_key, result, ttl_seconds=600)
        return result

    @staticmethod
    def _normalize_ta(data: dict, symbol: str, interval: str) -> dict:
        root = data.get("data", data) if data else {}
        signal = "NEUTRAL"
        score = 0.5

        if isinstance(root, dict):
            signal = str(
                root.get("signal")
                or root.get("recommendation")
                or root.get("trend")
                or "NEUTRAL"
            ).upper()
            for key in ("score", "confidence", "strength"):
                if key in root:
                    try:
                        score = float(root[key])
                        if score > 1:
                            score = score / 100.0
                        break
                    except (TypeError, ValueError):
                        pass
            indicators = root.get("indicators") or root.get("technical_indicators") or {}
        else:
            indicators = {}

        bullish = any(k in signal for k in ("BUY", "BULL", "UP", "LONG"))
        bearish = any(k in signal for k in ("SELL", "BEAR", "DOWN", "SHORT"))

        return {
            "symbol": symbol.upper(),
            "interval": interval,
            "signal": signal,
            "score": round(score, 3),
            "bias": "BULLISH" if bullish else "BEARISH" if bearish else "NEUTRAL",
            "indicators": indicators if isinstance(indicators, dict) else {},
            "source": "mock",
        }

    async def get_technical_analysis(self, symbol: str, interval: str = "1h") -> dict:
        """TA indicators from CMC MCP."""
        cache_key = f"mcp:ta:{symbol.upper()}:{interval}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        if not self._use_live_api():
            bias = random.choice(["BULLISH", "NEUTRAL", "BEARISH"])
            result = {
                "symbol": symbol.upper(),
                "interval": interval,
                "signal": "NEUTRAL",
                "score": random.uniform(0.4, 0.7),
                "bias": bias,
                "indicators": {},
                "source": "mock",
            }
            self.cache.set(cache_key, result, ttl_seconds=900)
            return result

        try:
            raw = await self._request(
                "technical/analysis",
                {"symbol": symbol.upper(), "interval": interval},
            )
            if raw:
                result = self._normalize_ta(raw, symbol, interval)
                result["source"] = "x402" if self.x402.enabled else "mcp"
                self.cache.set(cache_key, result, ttl_seconds=900)
                return result
        except Exception as e:
            logger.warning("MCP technical analysis failed for %s: %s", symbol, e)

        result = self._normalize_ta({}, symbol, interval)
        result["source"] = "mock_fallback"
        self.cache.set(cache_key, result, ttl_seconds=300)
        return result

    def get_x402_stats(self) -> dict:
        return self.x402.get_stats()

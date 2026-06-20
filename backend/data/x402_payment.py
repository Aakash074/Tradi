"""x402 micropayments for CoinMarketCap premium endpoints (USDC on Base)."""

import asyncio
import base64
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import urlencode, urlparse, urlunparse

import httpx

logger = logging.getLogger(__name__)

TwakX402Fn = Callable[[str, float], Awaitable[tuple[bool, str]]]


@dataclass
class X402Stats:
    payments_count: int = 0
    total_usd: float = 0.0
    failures: int = 0


@dataclass
class X402Payment:
    """
    Pay-per-request CMC data via x402 (EIP-3009 USDC on Base).

    Flow:
      1. GET endpoint → HTTP 402 + Payment-Required header
      2. TWAK wallet signs authorization (or paper mode skips)
      3. Retry with PAYMENT-SIGNATURE → JSON payload
    """

    max_amount_usdc: float = 0.01
    enabled: bool = False
    paper_mode: bool = True
    twak_request: Optional[TwakX402Fn] = None
    stats: X402Stats = field(default_factory=X402Stats)

    @staticmethod
    def parse_payment_required(headers: httpx.Headers) -> Optional[dict]:
        """Decode CMC Payment-Required header (base64 JSON or plain JSON)."""
        raw = headers.get("Payment-Required") or headers.get("payment-required")
        if not raw:
            return None
        try:
            decoded = base64.b64decode(raw).decode("utf-8")
            return json.loads(decoded)
        except Exception:
            try:
                return json.loads(raw)
            except Exception:
                logger.debug("Could not parse Payment-Required header")
                return None

    @staticmethod
    def _build_url(base_url: str, params: Optional[dict]) -> str:
        if not params:
            return base_url
        query = urlencode(params)
        parts = list(urlparse(base_url))
        parts[4] = query
        return urlunparse(parts)

    @staticmethod
    def _payment_amount_usd(payment_req: Optional[dict], default: float) -> float:
        if not payment_req:
            return default
        accepts = payment_req.get("accepts") or []
        if not accepts:
            return default
        try:
            # amount is USDC base units (6 decimals): 10000 = $0.01
            return int(accepts[0].get("amount", int(default * 1_000_000))) / 1_000_000
        except (TypeError, ValueError):
            return default

    async def pay_for_data(
        self,
        endpoint: str,
        params: Optional[dict] = None,
        max_amount_usdc: Optional[float] = None,
    ) -> Optional[dict]:
        """
        Fetch premium CMC data; pay up to max_amount_usdc per successful response.
        Returns None on failure (caller should fall back to free tier / mock).
        """
        if not self.enabled:
            return None

        max_pay = max_amount_usdc if max_amount_usdc is not None else self.max_amount_usdc
        url = self._build_url(endpoint, params)

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                probe = await client.get(url)
                if probe.status_code == 200:
                    return probe.json()

                if probe.status_code != 402:
                    probe.raise_for_status()

                payment_req = self.parse_payment_required(probe.headers)
                quoted = self._payment_amount_usd(payment_req, max_pay)
                if quoted > max_pay:
                    logger.warning(
                        "x402 quote $%.4f exceeds max $%.4f — skipping %s",
                        quoted,
                        max_pay,
                        endpoint,
                    )
                    self.stats.failures += 1
                    return None

                if self.paper_mode:
                    logger.debug("x402 paper mode — no USDC spent for %s", endpoint)
                    self.stats.failures += 1
                    return None

                if not self.twak_request:
                    logger.warning("x402 payment required but no TWAK wallet configured")
                    self.stats.failures += 1
                    return None

                ok, body = await self.twak_request(url, max_pay)
                if not ok:
                    logger.warning("x402 TWAK payment failed for %s: %s", endpoint, body[:200])
                    self.stats.failures += 1
                    return None

                data = self._parse_response_body(body)
                if data is None:
                    self.stats.failures += 1
                    return None

                self.stats.payments_count += 1
                self.stats.total_usd += quoted
                logger.info("x402 paid $%.4f for %s", quoted, endpoint)
                return data

        except httpx.HTTPStatusError as e:
            logger.warning("x402 HTTP error for %s: %s", endpoint, e)
            self.stats.failures += 1
            return None
        except Exception as e:
            logger.warning("x402 payment failed for %s: %s", endpoint, e)
            self.stats.failures += 1
            return None

    @staticmethod
    def _parse_response_body(body: str) -> Optional[dict]:
        body = (body or "").strip()
        if not body:
            return None
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            # TWAK may embed JSON after log lines — take last JSON object
            for line in reversed(body.splitlines()):
                line = line.strip()
                if line.startswith("{"):
                    try:
                        return json.loads(line)
                    except json.JSONDecodeError:
                        continue
        return None

    def get_stats(self) -> dict:
        return {
            "enabled": self.enabled,
            "payments_count": self.stats.payments_count,
            "total_cost_usd": round(self.stats.total_usd, 4),
            "failures": self.stats.failures,
            "max_payment_usdc": self.max_amount_usdc,
        }

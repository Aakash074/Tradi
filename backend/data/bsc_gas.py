"""BSC gas price for strategy-entry deferral (qualification trades bypass)."""

import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

BSC_RPC_URL = "https://bsc-dataseed.binance.org"
CACHE_TTL_SECONDS = 90

_cached_gwei: Optional[float] = None
_cached_at: float = 0.0


async def get_bsc_gas_gwei() -> Optional[float]:
    """
    Return current BSC gas price in gwei (eth_gasPrice).
    Cached ~90s. None on RPC failure (caller should fail-open).
    """
    global _cached_gwei, _cached_at
    now = time.monotonic()
    if _cached_gwei is not None and (now - _cached_at) < CACHE_TTL_SECONDS:
        return _cached_gwei

    payload = {"jsonrpc": "2.0", "method": "eth_gasPrice", "params": [], "id": 1}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(BSC_RPC_URL, json=payload)
            resp.raise_for_status()
            body = resp.json()
        hex_price = body.get("result")
        if not hex_price:
            return _cached_gwei
        gwei = int(hex_price, 16) / 1e9
        _cached_gwei = gwei
        _cached_at = now
        return gwei
    except Exception as e:
        logger.debug("BSC gas price fetch failed: %s", e)
        return _cached_gwei

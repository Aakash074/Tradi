"""Live OHLCV — CMC Pro (paid plans) with Binance public klines fallback."""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

CMC_OHLCV_URL = "https://pro-api.coinmarketcap.com/v2/cryptocurrency/ohlcv/historical"
BINANCE_KLINES_URL = "https://data-api.binance.vision/api/v3/klines"

STABLECOINS = frozenset({"USDT", "USDC", "DAI", "BUSD", "TUSD", "FDUSD", "USDD", "USD1"})

INTERVAL_TO_CMC_PERIOD = {
    "1h": "hourly",
    "1d": "daily",
    "1w": "weekly",
}

INTERVAL_TO_BINANCE = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}


def binance_symbol(cmc_symbol: str) -> Optional[str]:
    sym = cmc_symbol.upper()
    if sym in STABLECOINS:
        return None
    return f"{sym}USDT"


def parse_cmc_ohlcv(payload: dict, symbol: str) -> Optional[dict[str, list[float]]]:
    """Parse /v2/cryptocurrency/ohlcv/historical response."""
    if not payload or payload.get("status", {}).get("error_code"):
        return None

    data = payload.get("data")
    if not data:
        return None

    quotes: list = []
    if isinstance(data, dict):
        node = data.get(symbol.upper()) or data.get(symbol)
        if isinstance(node, list) and node:
            quotes = node[0].get("quotes", [])
        elif isinstance(node, dict):
            quotes = node.get("quotes", [])
        elif "quotes" in data:
            quotes = data.get("quotes", [])
    elif isinstance(data, list) and data:
        quotes = data[0].get("quotes", [])

    if not quotes:
        return None

    open_, high, low, close, volume = [], [], [], [], []
    for bar in quotes:
        usd = (bar.get("quote") or {}).get("USD") or bar.get("USD") or {}
        if not usd:
            continue
        try:
            open_.append(float(usd["open"]))
            high.append(float(usd["high"]))
            low.append(float(usd["low"]))
            close.append(float(usd["close"]))
            volume.append(float(usd.get("volume", 0)))
        except (KeyError, TypeError, ValueError):
            continue

    if not close:
        return None
    return {"open": open_, "high": high, "low": low, "close": close, "volume": volume}


def parse_binance_klines(rows: list) -> Optional[dict[str, list[float]]]:
    if not rows or not isinstance(rows, list) or isinstance(rows[0], dict):
        return None
    open_, high, low, close, volume = [], [], [], [], []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            continue
        open_.append(float(row[1]))
        high.append(float(row[2]))
        low.append(float(row[3]))
        close.append(float(row[4]))
        volume.append(float(row[5]))
    if not close:
        return None
    return {"open": open_, "high": high, "low": low, "close": close, "volume": volume}


async def fetch_cmc_ohlcv(
    symbol: str,
    interval: str,
    limit: int,
    api_key: str,
) -> Optional[dict[str, list[float]]]:
    time_period = INTERVAL_TO_CMC_PERIOD.get(interval)
    if not time_period or not api_key:
        return None

    params = {
        "symbol": symbol.upper(),
        "time_period": time_period,
        "count": min(limit, 500),
        "convert": "USD",
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                CMC_OHLCV_URL,
                params=params,
                headers={"X-CMC_PRO_API_KEY": api_key},
            )
            body = resp.json()
            err = body.get("status", {}).get("error_code", 0)
            if err == 1006:
                logger.debug("CMC OHLCV not on plan for %s — trying Binance", symbol)
                return None
            if err:
                logger.warning("CMC OHLCV error %s for %s: %s", err, symbol, body.get("status", {}).get("error_message"))
                return None
            resp.raise_for_status()
            return parse_cmc_ohlcv(body, symbol)
    except Exception as e:
        logger.warning("CMC OHLCV fetch failed for %s: %s", symbol, e)
        return None


async def fetch_binance_ohlcv(
    symbol: str,
    interval: str,
    limit: int,
) -> Optional[dict[str, list[float]]]:
    pair = binance_symbol(symbol)
    binance_interval = INTERVAL_TO_BINANCE.get(interval)
    if not pair or not binance_interval:
        return None

    params = {
        "symbol": pair,
        "interval": binance_interval,
        "limit": min(limit, 1000),
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(BINANCE_KLINES_URL, params=params)
            resp.raise_for_status()
            rows = resp.json()
            if isinstance(rows, dict) and rows.get("code"):
                logger.debug("Binance klines unavailable for %s (%s): %s", symbol, pair, rows.get("msg"))
                return None
            return parse_binance_klines(rows)
    except Exception as e:
        logger.debug("Binance OHLCV fetch failed for %s (%s): %s", symbol, pair, e)
        return None


async def fetch_live_ohlcv(
    symbol: str,
    interval: str,
    limit: int,
    cmc_api_key: str = "",
) -> tuple[Optional[dict[str, list[float]]], str]:
    """
    Returns (ohlcv dict, source tag).
    source: cmc | binance | none
    """
    if cmc_api_key:
        cmc = await fetch_cmc_ohlcv(symbol, interval, limit, cmc_api_key)
        if cmc:
            logger.debug("OHLCV %s %s from CMC (%d bars)", symbol, interval, len(cmc["close"]))
            return cmc, "cmc"

    bnb = await fetch_binance_ohlcv(symbol, interval, limit)
    if bnb:
        logger.debug("OHLCV %s %s from Binance (%d bars)", symbol, interval, len(bnb["close"]))
        return bnb, "binance"

    return None, "none"

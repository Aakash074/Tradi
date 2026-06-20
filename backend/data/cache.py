"""In-memory and TTL cache for market data."""

import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class CacheEntry:
    value: Any
    expires_at: float


class DataCache:
    DEFAULT_TTLS = {
        "price": 30,
        "ohlcv": 60,
        "funding": 3600,
        "sentiment": 900,
        "liquidity": 120,
    }

    def __init__(self):
        self._store: dict[str, CacheEntry] = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if not entry:
            return None
        if time.time() > entry.expires_at:
            del self._store[key]
            return None
        return entry.value

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        prefix = key.split(":")[0]
        ttl = ttl_seconds or self.DEFAULT_TTLS.get(prefix, 60)
        self._store[key] = CacheEntry(value=value, expires_at=time.time() + ttl)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()

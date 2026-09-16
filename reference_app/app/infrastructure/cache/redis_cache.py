from __future__ import annotations

import time
from typing import Any

from ...application.cache.ports import CachePort


class RedisCacheAdapter(CachePort):
    def __init__(self, redis_client: Any = None) -> None:
        self.client = redis_client

    def get(self, key: str) -> str | None:
        if self.client is None:
            return None
        try:
            val = self.client.get(key)
            if val is None:
                return None
            if isinstance(val, bytes):
                return val.decode("utf-8")
            return str(val)
        except Exception:
            return None

    def set(self, key: str, value: str, ttl_seconds: int = 300) -> None:
        if self.client is None:
            return
        try:
            self.client.set(key, value, ex=max(1, ttl_seconds))
        except Exception:
            pass

    def delete(self, key: str) -> None:
        if self.client is None:
            return
        try:
            self.client.delete(key)
        except Exception:
            pass

    def delete_prefix(self, prefix: str) -> None:
        if self.client is None:
            return
        try:
            pattern = f"{prefix}*"
            keys = list(self.client.scan_iter(match=pattern, count=100))
            if keys:
                self.client.delete(*keys)
        except Exception:
            pass


class MemoryCacheAdapter(CachePort):
    def __init__(self) -> None:
        self._store: dict[str, tuple[str, float]] = {}

    def get(self, key: str) -> str | None:
        item = self._store.get(key)
        if item is None:
            return None
        val, expiry = item
        if time.time() > expiry:
            self._store.pop(key, None)
            return None
        return val

    def set(self, key: str, value: str, ttl_seconds: int = 300) -> None:
        expiry = time.time() + max(1, ttl_seconds)
        self._store[key] = (value, expiry)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def delete_prefix(self, prefix: str) -> None:
        keys_to_del = [k for k in self._store if k.startswith(prefix)]
        for k in keys_to_del:
            self._store.pop(k, None)

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .ports import CachePort


@dataclass
class CacheService:
    cache: CachePort

    def get(self, key: str) -> str | None:
        try:
            return self.cache.get(key)
        except Exception:
            return None

    def set(self, key: str, value: str, ttl_seconds: int = 300) -> None:
        try:
            self.cache.set(key, value, ttl_seconds=ttl_seconds)
        except Exception:
            pass

    def delete(self, key: str) -> None:
        try:
            self.cache.delete(key)
        except Exception:
            pass

    def delete_prefix(self, prefix: str) -> None:
        try:
            self.cache.delete_prefix(prefix)
        except Exception:
            pass

    def get_or_set(
        self,
        key: str,
        factory: Callable[[], str],
        ttl_seconds: int = 300,
    ) -> str:
        cached = self.get(key)
        if cached is not None:
            return cached
        val = factory()
        self.set(key, val, ttl_seconds=ttl_seconds)
        return val

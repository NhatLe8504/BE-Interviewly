from __future__ import annotations

from typing import Any
import redis


def create_redis_client(url: str) -> redis.Redis:
    return redis.from_url(url, decode_responses=True)


def check_redis(client: Any) -> str:
    if client is None:
        return "down"
    try:
        return "up" if client.ping() else "down"
    except Exception:
        return "down"

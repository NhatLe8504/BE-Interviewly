from __future__ import annotations

import functools
import inspect
import json
from typing import Any, Callable

from fastapi.encoders import jsonable_encoder

EXCLUDED_KEY_PARAMS = {"session", "container", "request", "_user_id", "current_user", "credentials"}


def generate_cache_key(prefix: str, kwargs: dict[str, Any]) -> str:
    filtered = {
        k: v for k, v in kwargs.items()
        if k not in EXCLUDED_KEY_PARAMS and v is not None
    }
    if not filtered:
        return prefix

    param_parts = [f"{k}={filtered[k]}" for k in sorted(filtered.keys())]
    return f"{prefix}:{':'.join(param_parts)}"


def cache_response(ttl_seconds: int = 300, prefix: str = "cache"):
    def decorator(func: Callable):
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                container = kwargs.get("container")
                cache_service = getattr(container, "cache_service", None) if container else None
                if cache_service is None:
                    return await func(*args, **kwargs)

                cache_key = generate_cache_key(prefix, kwargs)
                cached = cache_service.get(cache_key)
                if cached is not None:
                    try:
                        return json.loads(cached)
                    except Exception:
                        pass

                result = await func(*args, **kwargs)
                try:
                    payload = json.dumps(jsonable_encoder(result), ensure_ascii=False)
                    cache_service.set(cache_key, payload, ttl_seconds=ttl_seconds)
                except Exception:
                    pass
                return result

            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            container = kwargs.get("container")
            cache_service = getattr(container, "cache_service", None) if container else None
            if cache_service is None:
                return func(*args, **kwargs)

            cache_key = generate_cache_key(prefix, kwargs)
            cached = cache_service.get(cache_key)
            if cached is not None:
                try:
                    return json.loads(cached)
                except Exception:
                    pass

            result = func(*args, **kwargs)
            try:
                payload = json.dumps(jsonable_encoder(result), ensure_ascii=False)
                cache_service.set(cache_key, payload, ttl_seconds=ttl_seconds)
            except Exception:
                pass
            return result

        return sync_wrapper

    return decorator


def invalidate_cache(container: Any, prefix: str) -> None:
    cache_service = getattr(container, "cache_service", None) if container else None
    if cache_service is not None:
        cache_service.delete_prefix(prefix)

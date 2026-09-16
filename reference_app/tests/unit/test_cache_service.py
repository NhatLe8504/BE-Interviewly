from __future__ import annotations

from unittest.mock import MagicMock
from app.application.cache.service import CacheService
from app.infrastructure.cache.redis_cache import MemoryCacheAdapter, RedisCacheAdapter
from app.presentation.api.helpers.cache import generate_cache_key


def test_memory_cache_adapter_crud():
    adapter = MemoryCacheAdapter()
    assert adapter.get("missing") is None

    adapter.set("key1", "val1", ttl_seconds=10)
    assert adapter.get("key1") == "val1"

    adapter.delete("key1")
    assert adapter.get("key1") is None


def test_memory_cache_delete_prefix():
    adapter = MemoryCacheAdapter()
    adapter.set("catalog:1", "data1")
    adapter.set("catalog:2", "data2")
    adapter.set("user:1", "userdata")

    adapter.delete_prefix("catalog:")
    assert adapter.get("catalog:1") is None
    assert adapter.get("catalog:2") is None
    assert adapter.get("user:1") == "userdata"


def test_redis_cache_adapter_delegation():
    mock_redis = MagicMock()
    mock_redis.get.return_value = b"hello"
    adapter = RedisCacheAdapter(mock_redis)

    assert adapter.get("test_key") == "hello"
    mock_redis.get.assert_called_with("test_key")

    adapter.set("test_key", "world", ttl_seconds=60)
    mock_redis.set.assert_called_with("test_key", "world", ex=60)

    adapter.delete("test_key")
    mock_redis.delete.assert_called_with("test_key")


def test_cache_service_get_or_set():
    adapter = MemoryCacheAdapter()
    service = CacheService(adapter)

    calls = 0
    def factory():
        nonlocal calls
        calls += 1
        return "expensive_result"

    res1 = service.get_or_set("k1", factory, ttl_seconds=60)
    assert res1 == "expensive_result"
    assert calls == 1

    # Second call should use cache, not increment calls
    res2 = service.get_or_set("k1", factory, ttl_seconds=60)
    assert res2 == "expensive_result"
    assert calls == 1


def test_generate_cache_key_normalizes_params():
    kwargs = {
        "session": object(),
        "container": object(),
        "request": object(),
        "domain_id": 5,
        "language": "vi",
        "level": None,
    }
    key = generate_cache_key("catalog:questions", kwargs)
    assert key == "catalog:questions:domain_id=5:language=vi"

    # Empty filtered kwargs
    empty_kwargs = {"session": object(), "container": object()}
    assert generate_cache_key("catalog:domains", empty_kwargs) == "catalog:domains"

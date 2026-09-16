from __future__ import annotations

import json


def test_catalog_domains_and_roles_are_cached(client):
    cache = client.app.state.services.cache_service
    cache.delete_prefix("catalog:")

    # 1. Fetch domains
    res1 = client.get("/api/v1/catalog/domains")
    assert res1.status_code == 200
    cached_domains = cache.get("catalog:domains")
    assert cached_domains is not None
    data1 = json.loads(cached_domains)
    assert isinstance(data1, list)
    assert len(data1) == len(res1.json())

    # 2. Fetch roles
    res2 = client.get("/api/v1/catalog/roles")
    assert res2.status_code == 200
    cached_roles = cache.get("catalog:roles")
    assert cached_roles is not None
    data2 = json.loads(cached_roles)
    assert isinstance(data2, list)
    assert len(data2) == len(res2.json())


def test_billing_plans_are_cached(client):
    cache = client.app.state.services.cache_service
    cache.delete("billing:plans")

    res = client.get("/api/v1/billing/plans")
    assert res.status_code == 200
    cached_plans = cache.get("billing:plans")
    assert cached_plans is not None
    data = json.loads(cached_plans)
    assert isinstance(data, list)
    assert len(data) == len(res.json())


def test_questions_query_key_caching(client):
    cache = client.app.state.services.cache_service
    cache.delete_prefix("catalog:questions")

    res = client.get("/api/v1/catalog/questions?limit=10&offset=0")
    assert res.status_code == 200

    # Key should be parameter-aware
    expected_key = "catalog:questions:limit=10:offset=0"
    cached_questions = cache.get(expected_key)
    assert cached_questions is not None
    data = json.loads(cached_questions)
    assert "items" in data
    assert "total" in data

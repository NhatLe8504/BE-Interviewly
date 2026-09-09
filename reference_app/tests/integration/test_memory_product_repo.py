from __future__ import annotations

import asyncio

from app.application.common import PageRequest
from app.application.products.ports import ProductFilter
from app.infrastructure.memory.product_repo import InMemoryProductRepository
from app.infrastructure.memory.state import MemoryState


def run(coro):
    return asyncio.run(coro)


def make_repo() -> tuple[InMemoryProductRepository, MemoryState]:
    state = MemoryState()
    state.seed()
    return InMemoryProductRepository(state), state


def test_seed_loads_products_and_warehouses() -> None:
    _, state = make_repo()
    assert len(state.products) == 3
    assert len(state.warehouses) == 2


def test_search_filters_by_name_or_sku() -> None:
    repo, _ = make_repo()
    result = run(repo.list_products(ProductFilter(search="widget"), PageRequest(page=1, size=20)))
    assert result.total == 2
    result = run(repo.list_products(ProductFilter(search="SKU-003"), PageRequest(page=1, size=20)))
    assert result.total == 1


def test_paging_slices_results() -> None:
    repo, _ = make_repo()
    first = run(repo.list_products(ProductFilter(search=""), PageRequest(page=1, size=2)))
    second = run(repo.list_products(ProductFilter(search=""), PageRequest(page=2, size=2)))
    assert (first.total, len(first.items)) == (3, 2)
    assert (second.total, len(second.items)) == (3, 1)


def test_reset_clears_state() -> None:
    repo, state = make_repo()
    state.reset()
    result = run(repo.list_products(ProductFilter(search=""), PageRequest(page=1, size=20)))
    assert result.total == 0
    assert run(repo.get_product("SKU-001")) is None

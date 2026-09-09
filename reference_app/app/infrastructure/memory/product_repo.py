from __future__ import annotations

from ...application.common import PageRequest, PageResult
from ...application.products.ports import ProductFilter
from ...domain.catalog import Product
from .state import MemoryState


class InMemoryProductRepository:
    def __init__(self, state: MemoryState) -> None:
        self._state = state

    async def list_products(
        self, filter: ProductFilter, page: PageRequest
    ) -> PageResult[Product]:
        query = filter.search.strip().lower()
        items = sorted(self._state.products.values(), key=lambda p: p.sku)
        if query:
            items = [
                p
                for p in items
                if query in p.sku.lower() or query in p.name.lower()
            ]
        total = len(items)
        window = items[page.offset : page.offset + page.size]
        return PageResult(items=tuple(window), total=total)

    async def get_product(self, sku: str) -> Product | None:
        return self._state.products.get(sku)

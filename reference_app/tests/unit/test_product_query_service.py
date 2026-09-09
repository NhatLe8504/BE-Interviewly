from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from app.application.common import PageRequest
from app.application.products.ports import ProductFilter
from app.application.products.query_service import ProductQueryService
from app.domain.catalog import Product
from app.domain.errors import NotFoundError


class FakeProductRepo:
    def __init__(self) -> None:
        self.items = [
            Product(sku="SKU-001", name="Widget A", price=Decimal("10")),
            Product(sku="SKU-002", name="Widget B", price=Decimal("20")),
        ]

    async def list_products(self, filter, page):
        return {"items": tuple(self.items), "total": len(self.items)}

    async def get_product(self, sku):
        for product in self.items:
            if product.sku == sku:
                return product
        return None


def run(coro):
    return asyncio.run(coro)


def test_list_delegates_to_port() -> None:
    service = ProductQueryService(FakeProductRepo())
    result = run(service.list(ProductFilter(search=""), PageRequest(page=1, size=20)))
    assert result["total"] == 2


def test_get_missing_product_raises_404() -> None:
    service = ProductQueryService(FakeProductRepo())
    with pytest.raises(NotFoundError):
        run(service.get("NOPE"))

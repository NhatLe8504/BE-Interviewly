from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ...domain.catalog import Product
from ..common import PageRequest, PageResult


@dataclass(frozen=True)
class ProductFilter:
    search: str = ""


class ProductQueryPort(Protocol):
    async def list_products(
        self, filter: ProductFilter, page: PageRequest
    ) -> PageResult[Product]:
        ...

    async def get_product(self, sku: str) -> Product | None:
        ...

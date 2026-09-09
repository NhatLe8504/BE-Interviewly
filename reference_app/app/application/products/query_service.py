from __future__ import annotations

from ...domain.catalog import Product
from ...domain.errors import NotFoundError
from ..common import PageRequest, PageResult
from .ports import ProductFilter, ProductQueryPort


class ProductQueryService:
    def __init__(self, repo: ProductQueryPort) -> None:
        self._repo = repo

    async def list(
        self, filter: ProductFilter, page: PageRequest
    ) -> PageResult[Product]:
        return await self._repo.list_products(filter, page)

    async def get(self, sku: str) -> Product:
        product = await self._repo.get_product(sku)
        if product is None:
            raise NotFoundError(f"product {sku} not found")
        return product

from __future__ import annotations

from pydantic import BaseModel


class ProductOut(BaseModel):
    sku: str
    name: str
    unit: str
    price: float

    @classmethod
    def from_entity(cls, product) -> "ProductOut":
        return cls(
            sku=product.sku,
            name=product.name,
            unit=product.unit,
            price=float(product.price),
        )


class PageProductOut(BaseModel):
    items: list[ProductOut]
    total: int
    page: int
    size: int

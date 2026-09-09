from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ....application.common import PageRequest
from ....application.products.ports import ProductFilter
from ..dependencies import get_product_service
from ..schemas.product import PageProductOut, ProductOut

router = APIRouter(prefix="/api/v1/products", tags=["products"])


@router.get("", response_model=PageProductOut)
async def list_products(
    search: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    service=Depends(get_product_service),
):
    result = await service.list(ProductFilter(search=search), PageRequest(page=page, size=size))
    return PageProductOut(
        items=[ProductOut.from_entity(p) for p in result.items],
        total=result.total,
        page=page,
        size=size,
    )


@router.get("/{sku}", response_model=ProductOut)
async def get_product(sku: str, service=Depends(get_product_service)):
    return ProductOut.from_entity(await service.get(sku))

from __future__ import annotations

from dataclasses import dataclass

from .movements.service import MovementService
from .products.query_service import ProductQueryService


@dataclass
class ServiceContainer:
    product_query_service: ProductQueryService
    movement_service: MovementService

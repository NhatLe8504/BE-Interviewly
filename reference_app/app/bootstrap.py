from __future__ import annotations

from .application.common import ClockPort
from .application.container import ServiceContainer
from .application.movements.service import MovementService
from .application.products.query_service import ProductQueryService
from .infrastructure.clock import SystemClock
from .infrastructure.memory.movement_repo import InMemoryMovementRepository
from .infrastructure.memory.product_repo import InMemoryProductRepository
from .infrastructure.memory.state import MemoryState
from .infrastructure.memory.warehouse_repo import InMemoryWarehouseRepository


def build_services(
    state: MemoryState | None = None,
    clock: ClockPort | None = None,
) -> ServiceContainer:
    state = state or MemoryState()
    if not state.products and not state.warehouses:
        state.seed()
    clock = clock or SystemClock()
    products = InMemoryProductRepository(state)
    warehouses = InMemoryWarehouseRepository(state)
    movements = InMemoryMovementRepository(state)
    return ServiceContainer(
        product_query_service=ProductQueryService(products),
        movement_service=MovementService(
            movements=movements,
            products=products,
            warehouses=warehouses,
            clock=clock,
        ),
    )

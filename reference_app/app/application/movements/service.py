from __future__ import annotations

from ...domain.errors import NotFoundError
from ...domain.movement import MovementLine, StockMovement
from ..common import ClockPort
from ..inventory.ports import WarehouseLookupPort
from ..products.ports import ProductQueryPort
from .commands import CreateMovementCommand
from .ports import MovementRepositoryPort


class MovementService:
    def __init__(
        self,
        *,
        movements: MovementRepositoryPort,
        products: ProductQueryPort,
        warehouses: WarehouseLookupPort,
        clock: ClockPort,
    ) -> None:
        self._movements = movements
        self._products = products
        self._warehouses = warehouses
        self._clock = clock

    async def create_draft(self, cmd: CreateMovementCommand) -> StockMovement:
        if not await self._warehouses.warehouse_exists(cmd.warehouse_code):
            raise NotFoundError(f"warehouse {cmd.warehouse_code} not found")
        lines: list[MovementLine] = []
        for item in cmd.lines:
            product = await self._products.get_product(item.sku)
            if product is None:
                raise NotFoundError(f"product {item.sku} not found")
            lines.append(
                MovementLine(
                    sku=item.sku,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                )
            )
        movement = StockMovement.create_draft(
            id=0,
            warehouse_code=cmd.warehouse_code,
            movement_type=cmd.movement_type,
            lines=lines,
            created_at=self._clock.now(),
        )
        return await self._movements.add(movement)

    async def list(self) -> tuple:
        return await self._movements.list()

    async def get(self, movement_id: int) -> StockMovement:
        for movement in await self._movements.list():
            if movement.id == movement_id:
                return movement
        raise NotFoundError(f"movement {movement_id} not found")

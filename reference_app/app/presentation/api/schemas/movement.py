from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from ....domain.movement import MovementType


class MovementLineCreate(BaseModel):
    sku: str = Field(min_length=1)
    quantity: int = Field(gt=0)
    unit_price: Decimal = Field(default=Decimal("0"), ge=0)


class StockMovementCreate(BaseModel):
    warehouse_code: str = Field(min_length=1)
    movement_type: MovementType
    lines: list[MovementLineCreate] = Field(min_length=1)


class MovementLineOut(BaseModel):
    sku: str
    quantity: int
    unit_price: float
    line_total: float


class StockMovementOut(BaseModel):
    id: int
    warehouse_code: str
    movement_type: MovementType
    status: str
    lines: list[MovementLineOut]
    total_amount: float
    created_at: datetime

    @classmethod
    def from_entity(cls, movement) -> "StockMovementOut":
        return cls(
            id=movement.id,
            warehouse_code=movement.warehouse_code,
            movement_type=movement.movement_type,
            status=movement.status.value,
            lines=[
                MovementLineOut(
                    sku=line.sku,
                    quantity=line.quantity,
                    unit_price=float(line.unit_price),
                    line_total=float(line.line_total),
                )
                for line in movement.lines
            ],
            total_amount=float(movement.total_amount),
            created_at=movement.created_at,
        )

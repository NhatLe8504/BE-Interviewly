from __future__ import annotations

import asyncio
import inspect
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.application.movements.commands import CreateMovementCommand, MovementLineInput
from app.application.movements.service import MovementService
from app.domain.catalog import Product
from app.domain.errors import NotFoundError
from app.domain.movement import MovementStatus, MovementType


class FakeMovements:
    def __init__(self) -> None:
        self.stored = []
        self.seq = 0

    async def add(self, movement):
        self.seq += 1
        object.__setattr__(movement, "id", self.seq)
        self.stored.append(movement)
        return movement

    async def list(self):
        return tuple(self.stored)


class FakeProducts:
    async def get_product(self, sku):
        if sku == "SKU-001":
            return Product(sku="SKU-001", name="Widget A", price=Decimal("10"))
        return None


class FakeWarehouses:
    async def warehouse_exists(self, code):
        return code == "WH-01"


class FixedClock:
    def now(self):
        return datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_service():
    return MovementService(
        movements=FakeMovements(),
        products=FakeProducts(),
        warehouses=FakeWarehouses(),
        clock=FixedClock(),
    )


def run(coro):
    return asyncio.run(coro)


def test_create_draft_returns_draft_without_stock_mutation() -> None:
    params = inspect.signature(MovementService.__init__).parameters
    assert "stock" not in " ".join(params).lower()
    service = make_service()
    movement = run(
        service.create_draft(
            CreateMovementCommand(
                warehouse_code="WH-01",
                movement_type=MovementType.IN,
                lines=(MovementLineInput(sku="SKU-001", quantity=2, unit_price=Decimal("10")),),
            )
        )
    )
    assert movement.status is MovementStatus.DRAFT
    assert movement.total_amount == Decimal("20")


def test_create_draft_unknown_warehouse_raises_404() -> None:
    service = make_service()
    with pytest.raises(NotFoundError):
        run(
            service.create_draft(
                CreateMovementCommand(
                    warehouse_code="WH-99",
                    movement_type=MovementType.IN,
                    lines=(MovementLineInput(sku="SKU-001", quantity=1),),
                )
            )
        )


def test_create_draft_unknown_product_raises_404() -> None:
    service = make_service()
    with pytest.raises(NotFoundError):
        run(
            service.create_draft(
                CreateMovementCommand(
                    warehouse_code="WH-01",
                    movement_type=MovementType.IN,
                    lines=(MovementLineInput(sku="NOPE", quantity=1),),
                )
            )
        )


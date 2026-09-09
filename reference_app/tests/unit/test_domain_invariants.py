from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.domain.catalog import Product
from app.domain.errors import DomainValidationError
from app.domain.movement import MovementLine, MovementStatus, MovementType, StockMovement


def test_product_rejects_empty_sku() -> None:
    with pytest.raises(DomainValidationError):
        Product(sku="  ", name="Widget")


def test_product_rejects_negative_price() -> None:
    with pytest.raises(DomainValidationError):
        Product(sku="SKU-1", name="Widget", price=Decimal("-1"))


def test_movement_line_rejects_zero_quantity() -> None:
    with pytest.raises(DomainValidationError):
        MovementLine(sku="SKU-1", quantity=0)


def test_movement_line_rejects_negative_price() -> None:
    with pytest.raises(DomainValidationError):
        MovementLine(sku="SKU-1", quantity=1, unit_price=Decimal("-1"))


def test_create_draft_rejects_empty_lines() -> None:
    with pytest.raises(DomainValidationError):
        StockMovement.create_draft(
            id=0,
            warehouse_code="WH-01",
            movement_type=MovementType.IN,
            lines=[],
            created_at=datetime.now(timezone.utc),
        )


def test_create_draft_computes_total() -> None:
    movement = StockMovement.create_draft(
        id=0,
        warehouse_code="WH-01",
        movement_type=MovementType.IN,
        lines=[
            MovementLine(sku="SKU-1", quantity=2, unit_price=Decimal("10.50")),
            MovementLine(sku="SKU-2", quantity=1, unit_price=Decimal("4")),
        ],
        created_at=datetime.now(timezone.utc),
    )
    assert movement.status is MovementStatus.DRAFT
    assert movement.total_amount == Decimal("25.00")

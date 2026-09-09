from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from ....application.movements.commands import CreateMovementCommand, MovementLineInput
from ..dependencies import get_movement_service
from ..schemas.movement import StockMovementCreate, StockMovementOut

router = APIRouter(prefix="/api/v1/movements", tags=["movements"])


@router.post("", response_model=StockMovementOut, status_code=status.HTTP_201_CREATED)
async def create_movement(
    payload: StockMovementCreate,
    response: Response,
    service=Depends(get_movement_service),
):
    command = CreateMovementCommand(
        warehouse_code=payload.warehouse_code,
        movement_type=payload.movement_type,
        lines=tuple(
            MovementLineInput(
                sku=line.sku,
                quantity=line.quantity,
                unit_price=line.unit_price,
            )
            for line in payload.lines
        ),
    )
    movement = await service.create_draft(command)
    response.headers["Location"] = f"/api/v1/movements/{movement.id}"
    return StockMovementOut.from_entity(movement)


@router.get("", response_model=list[StockMovementOut])
async def list_movements(service=Depends(get_movement_service)):
    return [StockMovementOut.from_entity(m) for m in await service.list()]


@router.get("/{movement_id}", response_model=StockMovementOut)
async def get_movement(movement_id: int, service=Depends(get_movement_service)):
    return StockMovementOut.from_entity(await service.get(movement_id))

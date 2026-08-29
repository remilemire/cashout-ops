# backend/app/features/cashout/data/router.py

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.features.auth.dependencies import require_admin
from app.infrastructure.db.dependencies import DbSession

from . import service as data_service
from .schemas import CashoutDataOut

router = APIRouter()


@router.get(
    "/data",
    response_model=list[CashoutDataOut],
    dependencies=[Depends(require_admin)],
)
async def list_data(
    db: DbSession,
) -> list[CashoutDataOut]:
    """List every reconciled cashout data row, newest first (admin only)."""
    data = await data_service.list_data(db)
    return [CashoutDataOut.model_validate(row) for row in data]


__all__ = ["router"]

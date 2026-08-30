# backend/app/features/cashout/data/router.py

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.features.auth.dependencies import require_admin
from app.infrastructure.db.dependencies import DbSession

from . import service as data_service
from .schemas import CashoutDataListOut

router = APIRouter()


@router.get(
    "/data",
    response_model=list[CashoutDataListOut],
    dependencies=[Depends(require_admin)],
)
async def list_data(
    db: DbSession,
) -> list[CashoutDataListOut]:
    """List every reconciled cashout data row, newest first (admin only)."""
    data = await data_service.list_data(db)
    return [CashoutDataListOut.model_validate(row) for row in data]


__all__ = ["router"]

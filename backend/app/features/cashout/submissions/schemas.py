# backend/app/features/cashout/submissions/schemas.py

from __future__ import annotations

import uuid

from app.core.schemas import BaseIn, BaseOut, UtcDateTime
from app.features.cashout.data.schemas import CashoutDataOut
from app.features.cashout.data.types import TipoutDepartment
from app.features.cashout.documents.schemas import CashoutDocumentOut
from app.features.users.schemas import UserOut

from .types import CashoutSubmissionStatus


class CashoutSubmissionOut(BaseOut):
    id: uuid.UUID
    created_at: UtcDateTime
    status: CashoutSubmissionStatus
    employee_user_id: uuid.UUID
    submitted_at: UtcDateTime
    completed_by_user_id: uuid.UUID | None = None
    first_completed_at: UtcDateTime | None = None
    # Last-completion snapshot; survives unsubmit. None means never completed.
    tipout_departments: list[TipoutDepartment] | None = None
    updated_at: UtcDateTime


class CashoutSubmissionListOut(CashoutSubmissionOut):
    employee: UserOut


class CashoutSubmissionDetailOut(CashoutSubmissionOut):
    employee: UserOut
    documents: list[CashoutDocumentOut]
    data: CashoutDataOut | None = None


class CashoutSubmissionComplete(BaseIn):
    tipout_departments: set[TipoutDepartment]


__all__ = [
    "CashoutSubmissionDetailOut",
    "CashoutSubmissionListOut",
    "CashoutSubmissionOut",
    "CashoutSubmissionComplete",
]

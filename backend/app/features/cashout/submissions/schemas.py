# backend/app/features/cashout/submissions/schemas.py

from __future__ import annotations

import uuid

from app.core.schemas import BaseOut, UtcDateTime
from app.features.cashout.data.schemas import CashoutDataOut
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
    updated_at: UtcDateTime


class CashoutSubmissionListOut(CashoutSubmissionOut):
    employee: UserOut


class CashoutSubmissionDetailOut(CashoutSubmissionOut):
    employee: UserOut
    documents: list[CashoutDocumentOut]
    data: CashoutDataOut | None = None


__all__ = [
    "CashoutSubmissionDetailOut",
    "CashoutSubmissionListOut",
    "CashoutSubmissionOut",
]

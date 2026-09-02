# backend/app/features/cashout/submissions/schemas.py

from __future__ import annotations

import uuid
from datetime import date

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
    # The day the cashout is for; submitted_at is when it was opened.
    business_date: date
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


class CashoutSubmissionCreate(BaseIn):
    # Omitted (or null) means today — see service.create_submission.
    business_date: date | None = None


class CashoutSubmissionUpdate(BaseIn):
    # Required: unlike creation there is no "today" default to fall back on.
    business_date: date


class CashoutSubmissionComplete(BaseIn):
    tipout_departments: set[TipoutDepartment]


__all__ = [
    "CashoutSubmissionCreate",
    "CashoutSubmissionDetailOut",
    "CashoutSubmissionListOut",
    "CashoutSubmissionOut",
    "CashoutSubmissionUpdate",
    "CashoutSubmissionComplete",
]

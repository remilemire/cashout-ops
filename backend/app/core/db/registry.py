# backend/app/core/db/registry.py

"""Imports every ORM model so Alembic autogenerate sees the full schema.

Models live in feature packages; importing them here registers them on
`Base.metadata`. Add new models to this file (or Alembic won't see them).
"""

from __future__ import annotations

from app.core.db.models import Base
from app.features.auth.models import EmailVerification, Session
from app.features.cashout.models import (
    CashoutData,
    CashoutDocument,
    CashoutDocumentAnalysis,
    CashoutSubmission,
)
from app.features.invitations.model import Invitation
from app.features.users.model import User

metadata = Base.metadata

__all__ = [
    "CashoutData",
    "CashoutDocument",
    "CashoutDocumentAnalysis",
    "CashoutSubmission",
    "EmailVerification",
    "Invitation",
    "Session",
    "User",
    "metadata",
]

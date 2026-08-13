# backend/app/infrastructure/db/registry.py

"""Imports every ORM model so Alembic autogenerate sees the full schema.

Models live in feature packages; importing them here registers them on
`Base.metadata`. Add new models to this file (or Alembic won't see them) —
via the owning feature's model surface, so a sub-feature can move without
this file noticing.
"""

from __future__ import annotations

from app.features.auth.models import ExternalIdentity
from app.features.cashout.models import (
    CashoutData,
    CashoutDocument,
    CashoutDocumentAnalysis,
    CashoutSubmission,
)
from app.features.users.model import User
from app.infrastructure.db.models import Base
from app.infrastructure.outbox.messages.model import OutboxMessage

metadata = Base.metadata

__all__ = [
    "CashoutData",
    "CashoutDocument",
    "CashoutDocumentAnalysis",
    "CashoutSubmission",
    "ExternalIdentity",
    "OutboxMessage",
    "User",
    "metadata",
]

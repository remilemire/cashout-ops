# backend/app/features/cashout/models/document.py

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db.models import Entity, enum_column
from app.features.cashout.types import CashoutDocumentType
from app.lib.documents import DocumentContentType

if TYPE_CHECKING:
    from app.features.users.model import User

    from .analysis import CashoutDocumentAnalysis
    from .submission import CashoutSubmission


class CashoutDocument(Entity):
    __tablename__ = "cashout_documents"

    # Non-nullable with an UNKNOWN default rather than nullable: UNKNOWN is also
    # a legitimate classification outcome (the AI may fail to classify), so a
    # NULL state would force consumers to handle two "no type" cases. "Not yet
    # analyzed" is distinguished by the absence/status of the analysis.
    document_type: Mapped[CashoutDocumentType] = mapped_column(
        enum_column(CashoutDocumentType, "cashout_document_type"),
        nullable=False,
        default=CashoutDocumentType.UNKNOWN,
        server_default=CashoutDocumentType.UNKNOWN.value,
    )
    content_type: Mapped[DocumentContentType] = mapped_column(
        enum_column(DocumentContentType, "document_content_type"), nullable=False
    )

    storage_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # SHA-256 of the stored bytes, for auditing what the AI analyzed.
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    cashout_submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cashout_submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cashout_submission: Mapped[CashoutSubmission] = relationship(
        back_populates="documents"
    )

    uploaded_by: Mapped[User] = relationship()

    analysis: Mapped[CashoutDocumentAnalysis | None] = relationship(
        back_populates="cashout_document", cascade="all, delete-orphan"
    )

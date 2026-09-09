# backend/app/features/cashout/documents/model.py

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.models import Base, enum_column
from app.lib.documents import DocumentContentType

if TYPE_CHECKING:
    from app.features.cashout.analyses.model import CashoutDocumentAnalysis
    from app.features.cashout.submissions.model import CashoutSubmission
    from app.features.users.model import User


class CashoutDocument(Base):
    __tablename__ = "cashout_documents"
    # Name the unique index explicitly: cashout/errors.py maps it to
    # DOCUMENT_DUPLICATE, and a unique-index violation reports the index name.
    __table_args__ = (
        Index(
            "ix_cashout_documents_submission_checksum",
            "cashout_submission_id",
            "checksum_sha256",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    cashout_submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cashout_submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # The classified document type lives on the analysis
    # (CashoutDocumentAnalysis.classification), not here.
    content_type: Mapped[DocumentContentType] = mapped_column(
        enum_column(DocumentContentType, "document_content_type"), nullable=False
    )

    storage_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # SHA-256 of the stored bytes: audits what the AI analyzed and rejects
    # duplicate uploads within a submission (unique with the submission id).
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    cashout_submission: Mapped[CashoutSubmission] = relationship(
        back_populates="documents"
    )

    uploaded_by: Mapped[User] = relationship()

    # One per document found in the upload, in the order they were found;
    # empty only between the upload and its first analysis being created,
    # which the intake workflow does in the same transaction.
    analyses: Mapped[list[CashoutDocumentAnalysis]] = relationship(
        back_populates="cashout_document",
        cascade="all, delete-orphan",
        order_by="CashoutDocumentAnalysis.position",
    )

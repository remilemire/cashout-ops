# backend/app/features/cashout/documents/model.py

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
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

    # The crop derived from the upload — its printed area, found by text
    # detection at upload time — stored as a sibling object. Null when there
    # is none: a PDF, an image with no detectable text, or cropping disabled
    # or failed at upload. Extraction reads the crop when it exists and the
    # original otherwise; the original stays the document of record either
    # way (its checksum, "view original").
    cropped_storage_key: Mapped[str | None] = mapped_column(
        String(512), nullable=True, unique=True
    )
    cropped_content_type: Mapped[DocumentContentType | None] = mapped_column(
        enum_column(DocumentContentType, "document_content_type"), nullable=True
    )
    # Where the crop sits in the upright original, in pixels:
    # {left, top, right, bottom}.
    crop_bounds: Mapped[dict[str, int] | None] = mapped_column(JSONB, nullable=True)

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

    analysis: Mapped[CashoutDocumentAnalysis | None] = relationship(
        back_populates="cashout_document", cascade="all, delete-orphan"
    )

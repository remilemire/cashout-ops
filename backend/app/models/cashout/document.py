# backend/app/models/cashout/document.py

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Entity, enum_column
from app.models.enums import CashoutDocumentType, DocumentContentType

if TYPE_CHECKING:
    from app.models.user import User

    from .ocr_result import CashoutOcrResult
    from .submission import CashoutSubmission


class CashoutDocument(Entity):
    __tablename__ = "cashout_documents"

    document_type: Mapped[CashoutDocumentType] = mapped_column(
        enum_column(CashoutDocumentType, "cashout_document_type"), nullable=False
    )
    content_type: Mapped[DocumentContentType] = mapped_column(
        enum_column(DocumentContentType, "document_content_type"), nullable=False
    )

    storage_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)

    uploaded_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    cashout_submission_id: Mapped[int] = mapped_column(
        ForeignKey("cashout_submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cashout_submission: Mapped[CashoutSubmission] = relationship(
        back_populates="documents"
    )

    uploaded_by: Mapped[User] = relationship()

    ocr_result: Mapped[CashoutOcrResult | None] = relationship(
        back_populates="cashout_document", cascade="all, delete-orphan"
    )

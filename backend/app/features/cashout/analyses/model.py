# backend/app/features/cashout/analyses/model.py

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.providers import AIProvider
from app.features.cashout.extraction.types import CashoutDocumentClassification
from app.infrastructure.db.models import Base, enum_column

from .types import DocumentAnalysisStatus

if TYPE_CHECKING:
    from app.features.cashout.documents.model import CashoutDocument
    from app.features.users.model import User


class CashoutDocumentAnalysis(Base):
    """One classification + extraction pass over a cashout document — an AI
    run, or its manually entered equivalent (null provider)."""

    __tablename__ = "cashout_document_analyses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # One analysis per document: a retry resets this row in place rather than
    # appending an attempt.
    cashout_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cashout_documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Null provider (and model) ⇔ a manually entered analysis: the user typed
    # the data in and no AI was involved.
    provider: Mapped[AIProvider | None] = mapped_column(
        enum_column(AIProvider, "ai_provider"), nullable=True
    )
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)

    status: Mapped[DocumentAnalysisStatus] = mapped_column(
        enum_column(DocumentAnalysisStatus, "document_analysis_status"),
        nullable=False,
        default=DocumentAnalysisStatus.EXTRACTING,
        server_default=DocumentAnalysisStatus.EXTRACTING.value,
    )

    # Set once an extraction completes; it stays null while one runs and on a
    # failed one — including a document the AI could not place, which fails
    # rather than being recorded under a classification of its own.
    classification: Mapped[CashoutDocumentClassification | None] = mapped_column(
        enum_column(CashoutDocumentClassification, "cashout_document_classification"),
        nullable=True,
    )
    # How confident the model was in the classification (0-1).
    classification_confidence: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )

    schema_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # The named schema's SCHEMA_VERSION when the data was written: which shape
    # extracted_data_json (and the verified data derived from it) follows.
    # Readers lift older shapes forward through the extraction registry's
    # upcasts, so the row stays readable after the schema changes.
    schema_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extracted_data_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    # How confident the model was in the extracted data (0-1), plus any fields
    # it flagged as uncertain/inconsistent ([{path, message}, ...]).
    extraction_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    issues: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)

    # Set when status is FAILED: the DocumentAIErrorCode value the extraction
    # failed with; error_code stays null for unexpected job crashes (only the
    # message is set).
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # When the analysis reached an outcome: the extraction completed (or
    # failed), or the manual entry was recorded.
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # The cashier-confirmed extraction: the extracted data as-is, or with the
    # corrections they submitted while verifying.
    verified_data_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    verified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    cashout_document: Mapped[CashoutDocument] = relationship(back_populates="analysis")

    verified_by: Mapped[User | None] = relationship()

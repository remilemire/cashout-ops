# backend/app/features/cashout/models/analysis.py

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db.models import Entity, enum_column
from app.features.cashout.types import CashoutDocumentType, DocumentAnalysisStatus
from app.integrations.ai import AIProvider

if TYPE_CHECKING:
    from .document import CashoutDocument


class CashoutDocumentAnalysis(Entity):
    """One AI classification + extraction pass over a cashout document."""

    __tablename__ = "cashout_document_analyses"

    provider: Mapped[AIProvider] = mapped_column(
        enum_column(AIProvider, "ai_provider"), nullable=False
    )
    model: Mapped[str] = mapped_column(String(100), nullable=False)

    status: Mapped[DocumentAnalysisStatus] = mapped_column(
        enum_column(DocumentAnalysisStatus, "document_analysis_status"),
        nullable=False,
        default=DocumentAnalysisStatus.PROCESSING,
        server_default=DocumentAnalysisStatus.PROCESSING.value,
    )

    classification: Mapped[CashoutDocumentType | None] = mapped_column(
        enum_column(CashoutDocumentType, "cashout_document_type"), nullable=True
    )
    # How confident the model was in the classification (0-1).
    classification_confidence: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )

    schema_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    extracted_data_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    # How confident the model was in the extracted data (0-1), plus any fields
    # it flagged as uncertain/inconsistent ([{path, message}, ...]).
    extraction_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    issues: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)

    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # One analysis per document: a retry resets this row in place rather than
    # appending an attempt.
    cashout_document_id: Mapped[int] = mapped_column(
        ForeignKey("cashout_documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    cashout_document: Mapped[CashoutDocument] = relationship(
        back_populates="analysis_result"
    )

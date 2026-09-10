# backend/app/features/cashout/analyses/model.py

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.providers import AIProvider
from app.features.cashout.extraction.types import CashoutDocumentClassification
from app.infrastructure.db.models import Base, enum_column
from app.lib.documents import DocumentContentType

from .types import DocumentAnalysisStatus

if TYPE_CHECKING:
    from app.features.cashout.uploads.model import CashoutUpload
    from app.features.users.model import User


class CashoutDocumentAnalysis(Base):
    """One classification + extraction pass over one document found in an
    upload — an AI run, or its manually entered equivalent (null provider).

    An upload holds one document until its first extraction finds more (two
    receipts in one photo, the pages of a PDF); each becomes its own analysis
    of the same CashoutUpload, reading its own crop.
    """

    __tablename__ = "cashout_document_analyses"
    __table_args__ = (
        UniqueConstraint(
            "cashout_upload_id",
            "position",
            name="uq_cashout_document_analyses_upload_position",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # A retry resets the row in place rather than appending an attempt; a
    # upload gains rows only for further documents found in it.
    cashout_upload_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cashout_uploads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Reading order among the document's analyses, 1-based: the order the
    # documents were found in the upload (page by page for a PDF). Unique
    # per upload.
    position: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
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

    # The crop this analysis reads — the one document among those found in
    # the upload — stored beside the original (in the original's format; PNG
    # for a PDF's rendered page), with where it sits in the upright original
    # ({left, top, right, bottom} pixels, plus `page` for a PDF). Kept
    # through resets and manual entry, so every rerun reads the same crop and
    # the card keeps previewing it. Null when the upload was read whole — no
    # detectable text, cropping switched off — or has not been extracted yet.
    cropped_storage_key: Mapped[str | None] = mapped_column(
        String(512), nullable=True, unique=True
    )
    cropped_content_type: Mapped[DocumentContentType | None] = mapped_column(
        enum_column(DocumentContentType, "document_content_type"), nullable=True
    )
    crop_bounds: Mapped[dict[str, int] | None] = mapped_column(JSONB, nullable=True)

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

    cashout_upload: Mapped[CashoutUpload] = relationship(back_populates="analyses")

    verified_by: Mapped[User | None] = relationship()

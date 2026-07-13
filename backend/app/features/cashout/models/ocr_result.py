# backend/app/features/cashout/models/ocr_result.py

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db.models import Entity, enum_column
from app.features.cashout.types import OcrProvider, OcrStatus

if TYPE_CHECKING:
    from .document import CashoutDocument


# TODO(document-ai): Rename this model/table to CashoutDocumentAnalysis. The AI
# consumes the original file directly, so this is not a traditional OCR result.
class CashoutOcrResult(Entity):
    __tablename__ = "cashout_ocr_results"

    provider: Mapped[OcrProvider] = mapped_column(
        enum_column(OcrProvider, "ocr_provider"), nullable=False
    )
    status: Mapped[OcrStatus] = mapped_column(
        enum_column(OcrStatus, "ocr_status"),
        nullable=False,
        default=OcrStatus.PROCESSING,
        server_default=OcrStatus.PROCESSING.value,
    )

    # TODO(document-ai): Replace raw_text/raw_response_json with explicit audit
    # fields: classification, confidence, provider, model, provider request ID,
    # schema name/version, extracted_data_json, checksum, and error code/message.
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_response_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # TODO(document-ai): Decide whether analyses are one-to-one or append-only
    # attempts. Remove unique=True if retries must be retained for audit.
    cashout_document_id: Mapped[int] = mapped_column(
        ForeignKey("cashout_documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    cashout_document: Mapped[CashoutDocument] = relationship(
        back_populates="ocr_result"
    )

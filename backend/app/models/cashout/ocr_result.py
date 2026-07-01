# backend/app/models/cashout/ocr_result.py

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Entity, enum_column
from app.models.enums import OcrProvider, OcrStatus

if TYPE_CHECKING:
    from .document import CashoutDocument


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

    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_response_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    cashout_document_id: Mapped[int] = mapped_column(
        ForeignKey("cashout_documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    cashout_document: Mapped[CashoutDocument] = relationship(
        back_populates="ocr_result"
    )

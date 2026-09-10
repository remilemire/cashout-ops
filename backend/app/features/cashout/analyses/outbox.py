"""Outbox message definition and handler for cashout analyses.

The upload and re-extract services enqueue `cashout.run_extraction` in their
request transaction; the handler runs the AI extraction at dispatch.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from pydantic import BaseModel

from app.core.outbox import OutboxMessageDefinition, OutboxMessageDefinitionList
from app.features.cashout.extraction import build_cashout_document_processor
from app.features.cashout.extraction.types import CashoutDocumentClassification

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.integrations.ai import AIClient
    from app.integrations.ocr import TextDetector
    from app.integrations.storage import DocumentStorageClient

logger = logging.getLogger(__name__)


type OutboxMessageType = Literal["cashout.run_extraction"]


class RunExtraction(BaseModel):
    analysis_id: UUID
    # A user-corrected classification to extract as, skipping AI
    # classification; None runs the full classify + extract pipeline.
    classification: CashoutDocumentClassification | None = None


_run_extraction_message: OutboxMessageDefinition[OutboxMessageType, RunExtraction] = (
    OutboxMessageDefinition("cashout.run_extraction", RunExtraction)
)

outbox_message_definitions: OutboxMessageDefinitionList[OutboxMessageType] = [
    _run_extraction_message
]


class RunExtractionOutboxHandler:
    """Runs the AI extraction for one analysis of an uploaded document."""

    message = _run_extraction_message

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        ai: AIClient,
        storage: DocumentStorageClient,
        text_detector: TextDetector | None,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._processor = build_cashout_document_processor(ai, storage, text_detector)

    async def handle(self, payload: RunExtraction) -> None:
        # Imported at call time: the outbox catalog imports cashout's root
        # outbox surface (and through it this module), and this sub-feature's
        # service imports the infrastructure outbox service to enqueue — a
        # module-level service import would close that cycle.
        from .service import run_extraction

        await run_extraction(
            self._sessionmaker,
            analysis_id=payload.analysis_id,
            processor=self._processor,
            classification=payload.classification,
        )

    async def on_dead_letter(self, payload: RunExtraction) -> None:
        # This callback only logs. A crash or failed recovery write may have
        # left the analysis EXTRACTING; dead-lettering does not repair it.
        logger.error(
            "Extraction outbox message dead-lettered for analysis %s",
            payload.analysis_id,
        )


__all__ = [
    "OutboxMessageType",
    "RunExtractionOutboxHandler",
    "outbox_message_definitions",
]

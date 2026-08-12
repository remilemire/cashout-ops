# backend/app/features/cashout/outbox.py

"""Outbox message definitions and handlers for the cashout feature.

The upload and re-extract services enqueue `cashout.run_extraction` in their
request transaction; the handler runs the AI extraction at dispatch.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from pydantic import BaseModel

from app.core.outbox import OutboxMessageDefinition, OutboxMessageDefinitionList

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from .extraction import CashoutDocumentProcessor

logger = logging.getLogger(__name__)


type OutboxMessageType = Literal["cashout.run_extraction"]


class RunExtraction(BaseModel):
    document_id: UUID


_run_extraction_message: OutboxMessageDefinition[OutboxMessageType, RunExtraction] = (
    OutboxMessageDefinition("cashout.run_extraction", RunExtraction)
)

outbox_message_definitions: OutboxMessageDefinitionList[OutboxMessageType] = [
    _run_extraction_message
]


class RunExtractionOutboxHandler:
    """Runs the AI extraction for an uploaded document."""

    message = _run_extraction_message

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        processor: CashoutDocumentProcessor,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._processor = processor

    async def handle(self, payload: RunExtraction) -> None:
        # Imported at call time: the outbox catalog imports this module, and
        # the service will import the outbox to enqueue — a module-level
        # service import would close that cycle.
        from .service import run_extraction

        await run_extraction(
            self._sessionmaker,
            document_id=payload.document_id,
            processor=self._processor,
        )

    async def on_dead_letter(self, payload: RunExtraction) -> None:
        # run_extraction already marks its analysis FAILED on any error, so
        # there is nothing to clean up here beyond making the loss visible.
        logger.error(
            "Extraction outbox message dead-lettered for document %s",
            payload.document_id,
        )


__all__ = [
    "OutboxMessageType",
    "RunExtractionOutboxHandler",
    "outbox_message_definitions",
]

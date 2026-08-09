# backend/app/features/cashout/outbox.py

"""Outbox message definitions and handlers for the cashout feature.

Defined but not yet wired: the upload/re-extract services still queue
`run_extraction` through PostCommitTasks; replacing that with `enqueue` is a
separate task.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel

from app.infrastructure.outbox.contracts import OutboxMessageDefinition

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from .extraction import CashoutDocumentProcessor

logger = logging.getLogger(__name__)


class RunExtraction(BaseModel):
    document_id: UUID


run_extraction_message = OutboxMessageDefinition(
    "cashout.run_extraction", RunExtraction
)

cashout_outbox_message_definitions: list[OutboxMessageDefinition] = [
    run_extraction_message
]


class RunExtractionOutboxHandler:
    """Runs the AI extraction for an uploaded document."""

    message = run_extraction_message

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
    "RunExtraction",
    "RunExtractionOutboxHandler",
    "cashout_outbox_message_definitions",
    "run_extraction_message",
]

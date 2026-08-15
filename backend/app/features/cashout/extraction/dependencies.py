# backend/app/features/cashout/extraction/dependencies.py

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.integrations.ai import AIClient
from app.integrations.ai.dependencies import get_ai_client
from app.integrations.storage import DocumentStorageClient
from app.integrations.storage.dependencies import get_document_storage

from .processor import CashoutDocumentProcessor, build_cashout_document_processor


def get_cashout_document_processor(
    ai: Annotated[AIClient, Depends(get_ai_client)],
    storage: Annotated[DocumentStorageClient, Depends(get_document_storage)],
) -> CashoutDocumentProcessor:
    return build_cashout_document_processor(ai, storage)


__all__ = ["get_cashout_document_processor"]

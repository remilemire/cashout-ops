from __future__ import annotations

from fastapi import Request

from app.features.cashout.extraction import CashoutDocumentProcessor


def get_cashout_document_processor(request: Request) -> CashoutDocumentProcessor:
    # TODO(document-ai): Return the application-scoped processor after the
    # lifespan owns construction and cleanup of AI and storage clients.
    raise NotImplementedError


__all__ = ["get_cashout_document_processor"]

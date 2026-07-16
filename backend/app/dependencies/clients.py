# backend/app/dependencies/clients.py

from __future__ import annotations

from fastapi import Request

from app.features.cashout.extraction import CashoutDocumentProcessor
from app.integrations.storage import DocumentStorageClient


def get_cashout_document_processor(request: Request) -> CashoutDocumentProcessor:
    return request.app.state.cashout_document_processor


def get_document_storage(request: Request) -> DocumentStorageClient:
    return request.app.state.document_storage


__all__ = ["get_cashout_document_processor", "get_document_storage"]

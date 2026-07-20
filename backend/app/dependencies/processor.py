# backend/app/dependencies/processor.py

from __future__ import annotations

from fastapi import Request

from app.features.cashout.extraction import CashoutDocumentProcessor


def get_cashout_document_processor(request: Request) -> CashoutDocumentProcessor:
    return request.app.state.cashout_document_processor


__all__ = ["get_cashout_document_processor"]

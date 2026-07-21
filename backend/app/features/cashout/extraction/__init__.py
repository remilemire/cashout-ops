# backend/app/features/cashout/extraction/__init__.py

from __future__ import annotations

from .processor import CashoutDocumentProcessingResult, CashoutDocumentProcessor

__all__ = ["CashoutDocumentProcessingResult", "CashoutDocumentProcessor"]

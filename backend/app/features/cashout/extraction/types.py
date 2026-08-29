# backend/app/features/cashout/extraction/types.py

from __future__ import annotations

from enum import StrEnum


# The document types the AI can classify a cashout document as. UNKNOWN is the
# explicit "none of the above": the model may pick it directly, and the
# processor folds a null classification into it — so a completed analysis
# always has a classification.
class CashoutDocumentClassification(StrEnum):
    TOUCHBISTRO_REPORT = "touchbistro_report"
    SERVER_SUMMARY_REPORT = "server_summary_report"
    UNKNOWN = "unknown"


__all__ = ["CashoutDocumentClassification"]

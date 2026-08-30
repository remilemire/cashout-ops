# backend/app/features/cashout/extraction/types.py

from __future__ import annotations

from enum import StrEnum


# The document types the AI can classify a cashout document as. There is no
# "none of the above" member: a document the model cannot place is a failed
# extraction (DocumentUnclassifiedError), not a classification — so every
# classification here has a registered extraction schema.
class CashoutDocumentClassification(StrEnum):
    TOUCHBISTRO_REPORT = "touchbistro_report"
    SERVER_SUMMARY_REPORT = "server_summary_report"


__all__ = ["CashoutDocumentClassification"]

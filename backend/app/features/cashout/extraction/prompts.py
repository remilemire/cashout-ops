# backend/app/features/cashout/extraction/prompts.py

"""The free-form guidance the processor gives the document AI.

Per-type signals are typed structures beside the schemas (the registry's
classification hints and the schemas' field hints); these are only the
framing that no per-type structure can carry.
"""

from __future__ import annotations

# Only the framing, the cross-type distinctions, and the "none of the above"
# guidance (markers can't describe the absence of a type).
CLASSIFY_INSTRUCTIONS = """
The document is one end-of-shift record from a restaurant cashout.

Leave the classification unset for anything else, including unrelated photos and documents too degraded to identify.

Distinguish carefully:

* A touchbistro_report is the point-of-sale end-of-day report, organized around sales categories and payment totals; a server_summary_report is the payment-terminal summary, organized around card transaction counts and totals.
* Both cover the same shift and repeat similar amounts, so classify on the document's own layout and headings rather than on the values it reports.
"""

EXTRACT_INSTRUCTIONS = """
The document is part of a restaurant cashout / end-of-shift reconciliation: a point-of-sale end-of-day report or a payment-terminal server summary. Similar values may repeat across sections. Read the area relevant to each requested field rather than the document in full.

Interpret fields by their accounting meaning and keep distinct concepts distinct — gross vs. net vs. total sales, individual tenders, collected vs. declared tips, tip-outs, refunds/voids/discounts, expected vs. submitted vs. owed vs. due cash, shortages vs. overages, transaction vs. settlement totals, and subtotal vs. tax vs. tip vs. final charged amount. Do not combine values from different documents or sections, and do not assume two similarly named totals represent the same accounting value.

For monetary values: preserve negative signs and explicit credits, treat amounts as Canadian dollars unless the document specifies another currency, do not convert currencies, do not recompute printed totals, and flag apparent inconsistencies rather than correcting them silently.

Handwritten values may be corrections or final accepted amounts; prefer them over printed values only when the document clearly indicates they replace or amend the printed value.
"""


__all__ = ["CLASSIFY_INSTRUCTIONS", "EXTRACT_INSTRUCTIONS"]

# backend/app/document_ai/fields.py

from __future__ import annotations

import re
from decimal import Decimal
from typing import Annotated

from pydantic import BeforeValidator, WithJsonSchema

# Presentation a printed amount carries that its value does not: currency
# symbols and ISO codes, digit grouping, and the assorted spaces a PDF text
# layer emits. Amounts are Canadian dollars unless the document says otherwise
# (see the extraction instructions), so "," is a thousands separator here.
_NOISE = re.compile(r"[$€£¥]|\b(?:CAD|USD)\b|[,\s  ]", re.IGNORECASE)


def _clean_money(value: object) -> object:
    """Strip the presentation a document puts around an amount.

    Runs on model output, so it is deliberately narrow: anything this does not
    recognize is handed to `Decimal` unchanged and fails validation there,
    rather than being coerced into a number that was never on the page.
    """
    if not isinstance(value, str):
        return value

    text = _NOISE.sub("", value)

    # Both accounting parentheses and a trailing sign mean a negative amount.
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative, text = True, text[1:-1]
    if text.endswith("-"):
        negative, text = True, text[:-1]
    if negative and not text.startswith("-"):
        text = f"-{text}"

    # Cleaning something away entirely leaves nothing to diagnose; let the
    # original reach Decimal so the validation error quotes what arrived.
    return text or value


# A monetary amount, as a plain decimal string.
#
# The JSON schema is stated outright rather than derived: Decimal's own schema
# is an anyOf over a number and a regex-patterned string, and `pattern` is a
# keyword provider structured-output modes have historically restricted. One
# unconstrained string keeps the payload inside the subset every provider
# accepts, and the description carries the encoding the type no longer does.
#
# This is the only text we put in a provider schema; per-field guidance stays
# in `FieldHint`, which never reaches the schema.
Money = Annotated[
    Decimal,
    BeforeValidator(_clean_money),
    WithJsonSchema(
        {
            "type": "string",
            "description": (
                'Amount as a plain decimal string, e.g. "1234.56". No currency'
                " symbol or separators. Negatives carry a leading minus sign."
            ),
        }
    ),
]


__all__ = ["Money"]

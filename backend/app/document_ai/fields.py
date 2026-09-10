from __future__ import annotations

import re
from decimal import Decimal
from typing import Annotated

from pydantic import BeforeValidator, WithJsonSchema

# Supported presentation characters. Commas are treated as grouping marks,
# regardless of currency; this parser does not infer locale or convert money.
_NOISE = re.compile(r"[$€£¥]|\b(?:CAD|USD)\b|[,\s  ]", re.IGNORECASE)


def _clean_money(value: object) -> object:
    """Strip supported currency symbols, grouping commas, and whitespace.

    Used for AI output and manual entries. Inputs must use a decimal point;
    comma placement is not validated, so decimal-comma input is unsupported.
    Accounting parentheses and a trailing minus are accepted. Remaining text
    is parsed by Decimal, which can reject invalid numeric syntax.
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
# Field-specific extraction guidance stays in FieldHint metadata. This
# description documents the shared monetary encoding in the JSON schema.
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

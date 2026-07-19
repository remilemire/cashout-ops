# backend/app/errors/validation/issues.py

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Literal, ReadOnly, TypedDict

type ValidationIssueCode = Literal[
    "EXTRA_FIELD",
    "MISSING_FIELD",
    "BOOLEAN_TYPE",
    "STRING_TYPE",
    "INTEGER_TYPE",
    "DECIMAL_TYPE",
    "OBJECT_TYPE",
    "TOO_SMALL",
    "TOO_LARGE",
    "TOO_SHORT",
    "TOO_LONG",
    "INVALID_OPTION",
    "INVALID_MULTIPLE",
    "INVALID_VALUE",
]


class ValidationIssueContext(TypedDict, total=False):
    min_value: ReadOnly[int]
    max_value: ReadOnly[int]
    min_length: ReadOnly[int]
    max_length: ReadOnly[int]
    multiple_of: ReadOnly[int]
    allowed_options: ReadOnly[Sequence[int | str | bool]]


validation_issue_catalog: _ValidationIssueCatalog = {
    "EXTRA_FIELD": {"create_message": lambda _: "This field isn't allowed."},
    "MISSING_FIELD": {"create_message": lambda _: "This field is required."},
    "BOOLEAN_TYPE": {"create_message": lambda _: "Enter true or false."},
    "STRING_TYPE": {"create_message": lambda _: "Enter valid text."},
    "INTEGER_TYPE": {"create_message": lambda _: "Enter a whole number."},
    "DECIMAL_TYPE": {"create_message": lambda _: "Enter a valid number."},
    "OBJECT_TYPE": {"create_message": lambda _: "Enter a valid object or list."},
    "TOO_SMALL": {
        "create_message": lambda ctx: (
            f"Must be greater than {ctx['min_value']}."
            if "min_value" in ctx
            else "Too small."
        ),
    },
    "TOO_LARGE": {
        "create_message": lambda ctx: (
            f"Must be less than {ctx['max_value']}."
            if "max_value" in ctx
            else "Too big."
        ),
    },
    "TOO_SHORT": {
        "create_message": lambda ctx: (
            f"Minimum {ctx['min_length']} characters required."
            if "min_length" in ctx
            else "Too short."
        ),
    },
    "TOO_LONG": {
        "create_message": lambda ctx: (
            f"Maximum {ctx['max_length']} characters allowed."
            if "max_length" in ctx
            else "Too long."
        ),
    },
    "INVALID_OPTION": {
        "create_message": lambda ctx: (
            f"Choose from: {' | '.join(str(option) for option in ctx['allowed_options'])}."
            if "allowed_options" in ctx
            else "Choose one of the allowed values."
        ),
    },
    "INVALID_MULTIPLE": {
        "create_message": lambda ctx: (
            f"Must be a multiple of {ctx['multiple_of']}."
            if "multiple_of" in ctx
            else "Enter a valid multiple."
        ),
    },
    "INVALID_VALUE": {
        "create_message": lambda _: "Invalid value.",
    },
}


class _ValidationIssueCatalogEntry(TypedDict):
    create_message: ReadOnly[Callable[[ValidationIssueContext], str]]


type _ValidationIssueCatalog = Mapping[
    ValidationIssueCode, _ValidationIssueCatalogEntry
]

__all__ = [
    "ValidationIssueCode",
    "ValidationIssueContext",
    "validation_issue_catalog",
]

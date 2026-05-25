# backend/app/errors/messages.py

from __future__ import annotations

from collections.abc import Callable, Mapping

from .types import ConflictCode, ErrorType, UnprocessableCode, UnprocessableContext

ERROR_MESSAGES: Mapping[ErrorType, str] = {
    "server_error": "Something went wrong.",
    "bad_request": "The request could not be processed.",
    "not_found": "The requested resource could not be found.",
    "unauthenticated": "Authentication required.",
    "forbidden": "You do not have permission to perform this action.",
    "conflict": "There was a conflict.",
    "unprocessable": "There was a problem with the submission.",
}


# ================================
# -------- Unprocessable ---------
# ================================


UNPROCESSABLE_MESSAGES: Mapping[UnprocessableCode, str] = {
    "extra_field": "This field isn't allowed.",
    "missing_field": "This field is required.",
    "boolean_type": "Enter true or false.",
    "string_type": "Enter valid text.",
    "integer_type": "Enter a whole number.",
    "decimal_type": "Enter a valid number.",
    "object_type": "Enter a valid object or list.",
    "too_small": "Too small.",
    "too_large": "Too big.",
    "too_short": "Too short.",
    "too_long": "Too Long.",
    "invalid_option": "Choose one of the allowed values.",
    "invalid_multiple": "Enter a valid multiple.",
}

CONTEXTUAL_UNPROCESSABLE_MESSAGES: Mapping[
    UnprocessableCode, Callable[[UnprocessableContext], str]
] = {
    "too_small": lambda ctx: (
        f"Must be greater than {ctx['min_value']}."
        if "min_value" in ctx
        else UNPROCESSABLE_MESSAGES["too_small"]
    ),
    "too_large": lambda ctx: (
        f"Must be less than {ctx['max_value']}."
        if "max_value" in ctx
        else UNPROCESSABLE_MESSAGES["too_large"]
    ),
    "too_short": lambda ctx: (
        f"Minimum {ctx['min_length']} characters required."
        if "min_length" in ctx
        else UNPROCESSABLE_MESSAGES["too_short"]
    ),
    "too_long": lambda ctx: (
        f"Maximum {ctx['max_length']} characters allowed."
        if "max_length" in ctx
        else UNPROCESSABLE_MESSAGES["too_long"]
    ),
    "invalid_option": lambda ctx: (
        f"Choose from: {' | '.join(f'{v}' for v in ctx['allowed_values'])}."
        if "allowed_values" in ctx
        else UNPROCESSABLE_MESSAGES["invalid_option"]
    ),
    "invalid_multiple": lambda ctx: (
        f"Must be a multiple of {ctx['multiple_of']}."
        if "multiple_of" in ctx
        else UNPROCESSABLE_MESSAGES["invalid_multiple"]
    ),
}


# ================================
# ----------- Conflict -----------
# ================================


CONFLICT_MESSAGES: Mapping[ConflictCode, str] = {
    "foreign_key": "Referenced item does not exist or is in use.",
    "unique": "Already exists.",
    "check": "Value does not satisfy constraints.",
    "integrity": "Integrity constraint violation.",
}

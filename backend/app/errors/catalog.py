# backend/app/errors/catalog.py

from __future__ import annotations

from collections.abc import Callable, Mapping

from fastapi import status

from .types import (
    ErrorCatalog,
    ErrorCode,
    UnprocessableContext,
    ValidationRule,
)

# ================================
# ---------- Validation ----------
# ================================

# Per-rule message builders. Each receives the validation ctx and returns a
# human-readable detail; rules without contextual data ignore it.
VALIDATION_DETAILS: Mapping[ValidationRule, Callable[[UnprocessableContext], str]] = {
    ValidationRule.EXTRA_FIELD: lambda ctx: "This field isn't allowed.",
    ValidationRule.MISSING_FIELD: lambda ctx: "This field is required.",
    ValidationRule.BOOLEAN_TYPE: lambda ctx: "Enter true or false.",
    ValidationRule.STRING_TYPE: lambda ctx: "Enter valid text.",
    ValidationRule.INTEGER_TYPE: lambda ctx: "Enter a whole number.",
    ValidationRule.DECIMAL_TYPE: lambda ctx: "Enter a valid number.",
    ValidationRule.OBJECT_TYPE: lambda ctx: "Enter a valid object or list.",
    ValidationRule.TOO_SMALL: lambda ctx: (
        f"Must be greater than {ctx['min_value']}."
        if "min_value" in ctx
        else "Too small."
    ),
    ValidationRule.TOO_LARGE: lambda ctx: (
        f"Must be less than {ctx['max_value']}." if "max_value" in ctx else "Too big."
    ),
    ValidationRule.TOO_SHORT: lambda ctx: (
        f"Minimum {ctx['min_length']} characters required."
        if "min_length" in ctx
        else "Too short."
    ),
    ValidationRule.TOO_LONG: lambda ctx: (
        f"Maximum {ctx['max_length']} characters allowed."
        if "max_length" in ctx
        else "Too long."
    ),
    ValidationRule.INVALID_OPTION: lambda ctx: (
        f"Choose from: {' | '.join(f'{v}' for v in ctx['allowed_values'])}."
        if "allowed_values" in ctx
        else "Choose one of the allowed values."
    ),
    ValidationRule.INVALID_MULTIPLE: lambda ctx: (
        f"Must be a multiple of {ctx['multiple_of']}."
        if "multiple_of" in ctx
        else "Enter a valid multiple."
    ),
    ValidationRule.INVALID_VALUE: lambda ctx: "Invalid value.",
}


# ================================
# ----------- Catalog ------------
# ================================


CATALOG: ErrorCatalog = {
    ErrorCode.SERVER_ERROR: {
        "error": "Server Error",
        "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
        "message": "Something went wrong.",
    },
    ErrorCode.BAD_REQUEST: {
        "error": "Bad Request",
        "status": status.HTTP_400_BAD_REQUEST,
        "message": "The request could not be processed.",
    },
    ErrorCode.UNAUTHORIZED: {
        "error": "Unauthorized",
        "status": status.HTTP_401_UNAUTHORIZED,
        "message": "Authentication required.",
    },
    ErrorCode.FORBIDDEN: {
        "error": "Forbidden",
        "status": status.HTTP_403_FORBIDDEN,
        "message": "You do not have permission to perform this action.",
    },
    ErrorCode.NOT_FOUND: {
        "error": "Not Found",
        "status": status.HTTP_404_NOT_FOUND,
        "message": "The requested resource could not be found.",
    },
    ErrorCode.IN_USE: {
        "error": "In Use",
        "status": status.HTTP_409_CONFLICT,
        "message": "Referenced item does not exist or is in use.",
    },
    ErrorCode.ALREADY_EXISTS: {
        "error": "Already Exists",
        "status": status.HTTP_409_CONFLICT,
        "message": "Already exists.",
    },
    ErrorCode.INVALID_STATE: {
        "error": "Invalid State",
        "status": status.HTTP_409_CONFLICT,
        "message": "The resource is not in a valid state for this action.",
    },
    ErrorCode.UNPROCESSABLE: {
        "error": "Unprocessable Entity",
        "status": status.HTTP_422_UNPROCESSABLE_CONTENT,
        "message": "There was a problem with the submission.",
        "details": VALIDATION_DETAILS,
    },
}

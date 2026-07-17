# backend/app/errors/openapi.py

from __future__ import annotations

from typing import Any

from .catalog import CATALOG
from .schemas import ErrorBody, ErrorDetail
from .types import ErrorCode, ValidationRule


def error_responses(*codes: ErrorCode) -> dict[int | str, dict[str, Any]]:
    """Build a FastAPI `responses` mapping documenting the given error codes.

    Codes sharing a status (the 409 family) are merged into a single response
    with one example per code. Pass the result as `responses=` on an app,
    router, or route; FastAPI merges the three levels per route.
    """
    by_status: dict[int, list[ErrorCode]] = {}
    for code in codes:
        by_status.setdefault(CATALOG[code]["status"], []).append(code)

    return {
        status: {
            "model": ErrorBody,
            "description": " / ".join(CATALOG[code]["error"] for code in status_codes),
            "content": {
                "application/json": {
                    "examples": {
                        code.value: {"value": _example_body(code)}
                        for code in status_codes
                    }
                }
            },
        }
        for status, status_codes in by_status.items()
    }


def _example_body(code: ErrorCode) -> dict[str, Any]:
    entry = CATALOG[code]
    body = ErrorBody(error=entry["error"], code=code, message=entry["message"])
    if code is ErrorCode.UNPROCESSABLE:
        body.errors = [ErrorDetail.build(ValidationRule.MISSING_FIELD, path=["field"])]
    return body.model_dump(by_alias=True, exclude_none=True, mode="json")

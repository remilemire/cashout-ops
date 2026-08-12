# backend/app/errors/openapi.py

from __future__ import annotations

from typing import Any

from .catalog import ErrorCode, error_catalog, kind_status_map
from .schemas import ErrorResponseSchema, ValidationIssueSchema
from .validation import validation_issue_catalog


def error_responses(*codes: ErrorCode) -> dict[int | str, dict[str, Any]]:
    """Build a FastAPI `responses` mapping documenting the given error codes.

    Codes sharing a status (e.g. the CONFLICT family) are merged into a single
    response with one example per code. Pass the result as `responses=` on an
    app, router, or route; FastAPI merges the three levels per route.
    """
    by_status: dict[int, list[ErrorCode]] = {}
    for code in codes:
        status = kind_status_map[error_catalog[code]["kind"]]
        by_status.setdefault(status, []).append(code)

    return {
        status: {
            "model": ErrorResponseSchema,
            "description": " / ".join(status_codes),
            "content": {
                "application/json": {
                    "examples": {
                        code: {"value": _example_body(code)} for code in status_codes
                    }
                }
            },
        }
        for status, status_codes in by_status.items()
    }


def _example_body(code: ErrorCode) -> dict[str, Any]:
    entry = error_catalog[code]
    issues = None
    if entry["kind"] == "VALIDATION":
        issues = [
            ValidationIssueSchema(
                code="MISSING_FIELD",
                path=["field"],
                message=validation_issue_catalog["MISSING_FIELD"]["create_message"]({}),
            )
        ]
    body = ErrorResponseSchema(
        kind=entry["kind"], code=code, message=entry["message"], issues=issues
    )
    return body.model_dump(by_alias=True, exclude_none=True, mode="json")


__all__ = ["error_responses"]

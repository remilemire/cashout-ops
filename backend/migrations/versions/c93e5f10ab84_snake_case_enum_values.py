"""Snake case enum values

Revision ID: c93e5f10ab84
Revises: b7d20c41a9e3
Create Date: 2026-08-13 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c93e5f10ab84"
down_revision: Union[str, Sequence[str], None] = "b7d20c41a9e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Every native enum label that changed, as {type: [(old, new), ...]}. user_role,
# oauth_issuer, and document_content_type are absent deliberately: the first two
# were already snake_case, and the third holds MIME types, which are not ours to
# reshape. RENAME VALUE rewrites the label in place, so existing rows keep
# pointing at it and no data has to be rewritten.
_ENUM_LABELS: dict[str, list[tuple[str, str]]] = {
    "cashout_submission_status": [
        ("PROCESSING", "processing"),
        ("COMPLETED", "completed"),
    ],
    "document_analysis_status": [
        ("EXTRACTING", "extracting"),
        ("NEEDS_VERIFICATION", "needs_verification"),
        ("VERIFIED", "verified"),
        ("FAILED", "failed"),
    ],
    "cashout_document_classification": [
        ("TOUCHBISTRO_SERVER_SHIFT_REPORT", "touchbistro_server_shift_report"),
        ("PAYSTONE_TERMINAL_REPORT", "paystone_terminal_report"),
        ("PAYMENT_RECEIPT", "payment_receipt"),
        ("DAILY_TIP_OUT_SHEET", "daily_tip_out_sheet"),
        ("DAILY_CASH_SUMMARY", "daily_cash_summary"),
        ("MANUAL_NOTE", "manual_note"),
        ("UNKNOWN", "unknown"),
    ],
    "ai_provider": [
        ("ANTHROPIC", "anthropic"),
        ("OPENAI", "openai"),
        ("GEMINI", "gemini"),
    ],
}

# Column defaults spell the label literally, so they are re-stated AFTER the
# rename in both directions — setting a default the type does not yet spell
# that way fails.
_SERVER_DEFAULTS: list[tuple[str, str, str, str]] = [
    ("cashout_submissions", "status", "PROCESSING", "processing"),
    ("cashout_document_analyses", "status", "EXTRACTING", "extracting"),
]

# cashout_document_analyses.error_code is a plain string column holding
# AIErrorCode values, so its rows are rewritten by data update.
_ERROR_CODES = [
    "SERVICE_UNAVAILABLE",
    "DOCUMENT_REJECTED",
    "UNREADABLE_DOCUMENT",
    "OUTPUT_LIMIT_REACHED",
    "UNSUPPORTED_FILE_TYPE",
]


def _rename_labels(*, to_snake: bool) -> None:
    for enum_name, labels in _ENUM_LABELS.items():
        for upper, lower in labels:
            old, new = (upper, lower) if to_snake else (lower, upper)
            op.execute(f"ALTER TYPE {enum_name} RENAME VALUE '{old}' TO '{new}'")


def _set_server_defaults(*, to_snake: bool) -> None:
    for table, column, upper, lower in _SERVER_DEFAULTS:
        value = lower if to_snake else upper
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT '{value}'")


def _rewrite_error_codes(*, to_snake: bool) -> None:
    for upper in _ERROR_CODES:
        old, new = (upper, upper.lower()) if to_snake else (upper.lower(), upper)
        op.execute(
            "UPDATE cashout_document_analyses SET error_code = "
            f"'{new}' WHERE error_code = '{old}'"
        )


def upgrade() -> None:
    """Upgrade schema: enum values become lower snake_case.

    The labels are renamed in place, so persisted rows stay valid throughout
    and no table is rewritten.
    """
    _rename_labels(to_snake=True)
    _set_server_defaults(to_snake=True)
    _rewrite_error_codes(to_snake=True)


def downgrade() -> None:
    """Downgrade schema: restore the SCREAMING_SNAKE_CASE labels."""
    _rename_labels(to_snake=False)
    _set_server_defaults(to_snake=False)
    _rewrite_error_codes(to_snake=False)

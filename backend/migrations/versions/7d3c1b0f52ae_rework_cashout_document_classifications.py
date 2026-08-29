"""Rework the cashout document classifications

Revision ID: 7d3c1b0f52ae
Revises: 932beaca5e6e
Create Date: 2026-08-28 00:00:00.000000

"""

from typing import Mapping, Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7d3c1b0f52ae"
down_revision: Union[str, Sequence[str], None] = "932beaca5e6e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Hand-written: autogenerate does not detect enum member changes.
#
# The real extraction schemas cover exactly two document types, so the five
# speculative ones go. Postgres cannot remove an enum label, so the type is
# recreated in both directions and the column cast through a CASE.

_NEW_VALUES = ("touchbistro_report", "server_summary_report", "unknown")

_OLD_VALUES = (
    "touchbistro_server_shift_report",
    "paystone_terminal_report",
    "payment_receipt",
    "daily_tip_out_sheet",
    "daily_cash_summary",
    "manual_note",
    "unknown",
)

# Labels that survive, under their new spelling. Anything else lands on
# 'unknown', not NULL: its document was never extracted against a real schema,
# and UNKNOWN is how a completed analysis says "could not place it" — NULL
# means extraction has not finished.
_UPGRADE_RENAMES = {"touchbistro_server_shift_report": "touchbistro_report"}

# Reversing is lossy: the collapsed types cannot be told apart afterwards, so
# every 'unknown' stays 'unknown'.
_DOWNGRADE_RENAMES = {"touchbistro_report": "touchbistro_server_shift_report"}


def _cast_expression(values: Sequence[str], renames: Mapping[str, str]) -> str:
    """Map each existing label onto one the new type spells."""
    # An unfinished analysis has no classification yet; keep it that way.
    branches = ["WHEN classification IS NULL THEN NULL"]
    branches += [
        f"WHEN classification::text = '{old}' THEN '{new}'"
        for old, new in renames.items()
    ]
    kept = ", ".join(f"'{value}'" for value in values)
    branches.append(f"WHEN classification::text IN ({kept}) THEN classification::text")
    return f"CASE {' '.join(branches)} ELSE 'unknown' END"


def _recreate_enum(values: Sequence[str], renames: Mapping[str, str]) -> None:
    op.execute(
        "ALTER TYPE cashout_document_classification"
        " RENAME TO cashout_document_classification_old"
    )
    labels = ", ".join(f"'{value}'" for value in values)
    op.execute(f"CREATE TYPE cashout_document_classification AS ENUM ({labels})")
    op.execute(
        "ALTER TABLE cashout_document_analyses ALTER COLUMN classification"
        " TYPE cashout_document_classification"
        f" USING ({_cast_expression(values, renames)})::cashout_document_classification"
    )
    op.execute("DROP TYPE cashout_document_classification_old")


def upgrade() -> None:
    """Keep only the two classifications the extraction schemas cover."""
    _recreate_enum(_NEW_VALUES, _UPGRADE_RENAMES)


def downgrade() -> None:
    """Restore the speculative classifications (collapsed rows stay collapsed)."""
    _recreate_enum(_OLD_VALUES, _DOWNGRADE_RENAMES)

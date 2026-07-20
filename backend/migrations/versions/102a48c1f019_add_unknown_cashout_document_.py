"""Add UNKNOWN cashout document classification

Revision ID: 102a48c1f019
Revises: 6c4e4b01629d
Create Date: 2026-07-19 00:03:02.911835

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "102a48c1f019"
down_revision: Union[str, Sequence[str], None] = "6c4e4b01629d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Hand-written: autogenerate does not detect enum member changes.

_KNOWN_VALUES = (
    "TOUCHBISTRO_SERVER_SHIFT_REPORT",
    "PAYSTONE_TERMINAL_REPORT",
    "PAYMENT_RECEIPT",
    "DAILY_TIP_OUT_SHEET",
    "DAILY_CASH_SUMMARY",
    "MANUAL_NOTE",
)


def upgrade() -> None:
    """Add the UNKNOWN member to the classification enum."""
    # Allowed inside a transaction since Postgres 12, as long as the new value
    # isn't used in the same transaction.
    op.execute("ALTER TYPE cashout_document_classification ADD VALUE 'UNKNOWN'")


def downgrade() -> None:
    """Recreate the enum without UNKNOWN (Postgres cannot drop a value)."""
    op.execute(
        "UPDATE cashout_document_analyses SET classification = NULL"
        " WHERE classification = 'UNKNOWN'"
    )
    op.execute(
        "ALTER TYPE cashout_document_classification"
        " RENAME TO cashout_document_classification_old"
    )
    values = ", ".join(f"'{value}'" for value in _KNOWN_VALUES)
    op.execute(f"CREATE TYPE cashout_document_classification AS ENUM ({values})")
    op.execute(
        "ALTER TABLE cashout_document_analyses ALTER COLUMN classification"
        " TYPE cashout_document_classification"
        " USING classification::text::cashout_document_classification"
    )
    op.execute("DROP TYPE cashout_document_classification_old")

"""classification without unknown

A document the AI cannot place is a failed extraction, not a classification:
`unknown` leaves the classification enum and existing analyses holding it are
converted to the failed state the extraction now produces. Shipped as its own
revision (rather than an edit to the applied initial migration) so existing
databases pick the change up from `alembic upgrade head`.

Revision ID: 4c8f21d0a7b3
Revises: 978ee6ba7960
Create Date: 2026-08-29 23:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4c8f21d0a7b3"
down_revision: Union[str, Sequence[str], None] = "978ee6ba7960"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ENUM_NAME = "cashout_document_classification"
VALUES = ("touchbistro_report", "server_summary_report")
# Kept in sync with analyses/messages.py, which maps the persisted error_code
# to this text for every analysis the extraction fails this way.
UNCLASSIFIED_MESSAGE = (
    "This doesn't look like a cashout report. Retry, replace it with a "
    "clearer copy, or enter the details manually."
)


def _replace_enum(values: Sequence[str]) -> None:
    """Swap the classification enum type for one over exactly `values`.

    Postgres cannot drop a value from an enum, so the type is rebuilt and the
    column recast onto it.
    """
    members = ", ".join(f"'{value}'" for value in values)
    op.execute(f"ALTER TYPE {ENUM_NAME} RENAME TO {ENUM_NAME}_old")
    op.execute(f"CREATE TYPE {ENUM_NAME} AS ENUM ({members})")
    op.execute(
        "ALTER TABLE cashout_document_analyses ALTER COLUMN classification "
        f"TYPE {ENUM_NAME} USING classification::text::{ENUM_NAME}"
    )
    op.execute(f"DROP TYPE {ENUM_NAME}_old")


def upgrade() -> None:
    # Converted before the type is rebuilt: an analysis still holding
    # `unknown` becomes the failure it would be today (nothing was extracted
    # from it, so nothing is lost), which the cashier resolves by retrying,
    # replacing the document, or entering its details manually.
    op.execute(
        sa.text(
            """
            UPDATE cashout_document_analyses
            SET status = 'failed',
                classification = NULL,
                error_code = 'unclassifiable_document',
                error_message = :message,
                completed_at = COALESCE(completed_at, now())
            WHERE classification = 'unknown'
            """
        ).bindparams(message=UNCLASSIFIED_MESSAGE)
    )
    _replace_enum(VALUES)


def downgrade() -> None:
    # The value comes back, but the analyses converted above do not: they are
    # indistinguishable from any other failed extraction now, and a retry
    # reproduces the outcome either way.
    _replace_enum((*VALUES, "unknown"))

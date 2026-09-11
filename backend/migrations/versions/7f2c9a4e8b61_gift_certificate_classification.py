"""Add the gift certificate document classification to existing databases.

Revision ID: 7f2c9a4e8b61
Revises: e5a3c7d19f84
Create Date: 2026-09-11 00:30:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "7f2c9a4e8b61"
down_revision: Union[str, Sequence[str], None] = "e5a3c7d19f84"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS also accepts a database rebuilt during the initial rollout,
    # when this value was temporarily included in the historical migrations.
    op.execute(
        "ALTER TYPE cashout_document_classification "
        "ADD VALUE IF NOT EXISTS 'gift_certificate'"
    )


def downgrade() -> None:
    # Postgres cannot remove an enum value directly. The cast deliberately
    # fails if certificates still use it, rolling back without discarding data.
    op.execute(
        "ALTER TYPE cashout_document_classification "
        "RENAME TO cashout_document_classification_old"
    )
    op.execute(
        "CREATE TYPE cashout_document_classification AS ENUM "
        "('touchbistro_report', 'server_summary_report')"
    )
    op.execute(
        "ALTER TABLE cashout_document_analyses ALTER COLUMN classification "
        "TYPE cashout_document_classification "
        "USING classification::text::cashout_document_classification"
    )
    op.execute("DROP TYPE cashout_document_classification_old")

"""several analyses per document

An upload may hold several documents — two receipts on the table, the pages
of a PDF — and the first extraction now finds them and gives each its own
analysis (with its own crop, verification, and retries). The one-analysis-
per-document uniqueness becomes a plain index, and `position` orders a
document's analyses in the reading order they were found in. Shipped as its
own revision so existing databases pick the change up from `alembic upgrade
head`; every existing analysis is its document's first.

Revision ID: a1d4e7f92b36
Revises: 3e7a1c9d5f42
Create Date: 2026-09-09 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1d4e7f92b36"
down_revision: Union[str, Sequence[str], None] = "3e7a1c9d5f42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DOCUMENT_INDEX = "ix_cashout_document_analyses_cashout_document_id"
_POSITION_CONSTRAINT = "uq_cashout_document_analyses_document_position"


def upgrade() -> None:
    op.drop_index(_DOCUMENT_INDEX, table_name="cashout_document_analyses")
    op.create_index(
        _DOCUMENT_INDEX,
        "cashout_document_analyses",
        ["cashout_document_id"],
        unique=False,
    )
    # Existing analyses are each their document's only one: position 1.
    op.add_column(
        "cashout_document_analyses",
        sa.Column("position", sa.Integer(), server_default="1", nullable=False),
    )
    op.create_unique_constraint(
        _POSITION_CONSTRAINT,
        "cashout_document_analyses",
        ["cashout_document_id", "position"],
    )


def downgrade() -> None:
    # Back to one analysis per document: only each document's first survives.
    op.execute("DELETE FROM cashout_document_analyses WHERE position <> 1")
    op.drop_constraint(
        _POSITION_CONSTRAINT, "cashout_document_analyses", type_="unique"
    )
    op.drop_column("cashout_document_analyses", "position")
    op.drop_index(_DOCUMENT_INDEX, table_name="cashout_document_analyses")
    op.create_index(
        _DOCUMENT_INDEX,
        "cashout_document_analyses",
        ["cashout_document_id"],
        unique=True,
    )

"""nullable analysis provider

Manual document entry records an analysis with no AI involved: a null
provider/model marks it as manually entered. Shipped as its own revision
(rather than an edit to the applied initial migration) so existing databases
pick the change up from `alembic upgrade head`.

Revision ID: 978ee6ba7960
Revises: f6c0323b07d2
Create Date: 2026-08-29 22:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "978ee6ba7960"
down_revision: Union[str, Sequence[str], None] = "f6c0323b07d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "cashout_document_analyses",
        "provider",
        existing_type=sa.Enum("anthropic", "openai", "gemini", name="ai_provider"),
        nullable=True,
    )
    op.alter_column(
        "cashout_document_analyses",
        "model",
        existing_type=sa.String(length=100),
        nullable=True,
    )


def downgrade() -> None:
    # Fails if manually entered (null-provider) analyses exist; delete them
    # first if the downgrade is truly intended.
    op.alter_column(
        "cashout_document_analyses",
        "model",
        existing_type=sa.String(length=100),
        nullable=False,
    )
    op.alter_column(
        "cashout_document_analyses",
        "provider",
        existing_type=sa.Enum("anthropic", "openai", "gemini", name="ai_provider"),
        nullable=False,
    )

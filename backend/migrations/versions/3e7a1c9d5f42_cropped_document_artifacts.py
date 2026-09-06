"""cropped document artifacts

Each uploaded image may carry a crop of its printed area, produced by text
detection at upload time, stored beside the original, and read by the AI in
its place. Shipped as its own revision (rather than an edit to the applied
initial migration) so existing databases pick the change up from `alembic
upgrade head`; documents uploaded before cropping stay uncropped (null) and
extract from the original as they always did.

Revision ID: 3e7a1c9d5f42
Revises: b8e1d47c5a92
Create Date: 2026-09-05 23:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "3e7a1c9d5f42"
down_revision: Union[str, Sequence[str], None] = "b8e1d47c5a92"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Postgres's own name for a single-column unique constraint, which is what
# create_all gives the model's `unique=True`; kept identical so a fresh
# install and a migrated one match.
_CROPPED_KEY_CONSTRAINT = "cashout_documents_cropped_storage_key_key"


def upgrade() -> None:
    op.add_column(
        "cashout_documents",
        sa.Column("cropped_storage_key", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "cashout_documents",
        sa.Column(
            "cropped_content_type",
            # The enum type already exists (the original's content_type).
            postgresql.ENUM(
                "image/jpeg",
                "image/png",
                "image/webp",
                "application/pdf",
                name="document_content_type",
                create_type=False,
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "cashout_documents",
        sa.Column(
            "crop_bounds", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    op.create_unique_constraint(
        _CROPPED_KEY_CONSTRAINT, "cashout_documents", ["cropped_storage_key"]
    )


def downgrade() -> None:
    # The stored crop objects are not removed: nothing in the schema points
    # at them any more, and the originals are untouched.
    op.drop_constraint(_CROPPED_KEY_CONSTRAINT, "cashout_documents", type_="unique")
    op.drop_column("cashout_documents", "crop_bounds")
    op.drop_column("cashout_documents", "cropped_content_type")
    op.drop_column("cashout_documents", "cropped_storage_key")

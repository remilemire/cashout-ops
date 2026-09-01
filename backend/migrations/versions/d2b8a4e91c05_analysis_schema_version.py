"""analysis schema version

Each analysis records the SCHEMA_VERSION its extracted data was written
under, so a stored payload stays readable (via the extraction registry's
upcasts) after the schema it follows changes shape. Shipped as its own
revision (rather than an edit to the applied initial migration) so existing
databases pick the change up from `alembic upgrade head`.

Revision ID: d2b8a4e91c05
Revises: e8f4a2b19c67
Create Date: 2026-09-01 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d2b8a4e91c05"
down_revision: Union[str, Sequence[str], None] = "e8f4a2b19c67"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cashout_document_analyses",
        sa.Column("schema_version", sa.Integer(), nullable=True),
    )
    # Every pre-versioning extraction was written by a version-1 schema — the
    # only version that has existed. Rows with no schema captured (failed or
    # in-flight analyses) stay null, like their schema_name.
    op.execute(
        "UPDATE cashout_document_analyses"
        " SET schema_version = 1 WHERE schema_name IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("cashout_document_analyses", "schema_version")

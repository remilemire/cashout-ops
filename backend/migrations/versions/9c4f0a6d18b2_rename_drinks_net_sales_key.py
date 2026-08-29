"""Rename the drinks_net_sales extraction key

Revision ID: 9c4f0a6d18b2
Revises: 4e8b21c7af35
Create Date: 2026-08-29 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9c4f0a6d18b2"
down_revision: Union[str, Sequence[str], None] = "4e8b21c7af35"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# TouchBistroReportData.drinks_net_sales became drink_net_sales, matching the
# cashout_data column it reconciles into. The extraction payloads are stored
# JSONB keyed by field name, so rows written before the rename still carry the
# old key and reconciliation would not find them.
#
# A pure key rename: the value is untouched, so no extracted figure changes.
_COLUMNS = ("extracted_data_json", "verified_data_json")


def _rename_key(old: str, new: str) -> None:
    for column in _COLUMNS:
        # jsonb_exists() rather than the ? operator, which a DBAPI would read
        # as a bind placeholder.
        op.execute(
            f"UPDATE cashout_document_analyses SET {column} ="
            f" ({column} - '{old}')"
            f" || jsonb_build_object('{new}', {column} -> '{old}')"
            f" WHERE jsonb_exists({column}, '{old}')"
        )


def upgrade() -> None:
    """Re-key stored extractions onto the field's new name."""
    _rename_key("drinks_net_sales", "drink_net_sales")


def downgrade() -> None:
    """Restore the old key."""
    _rename_key("drink_net_sales", "drinks_net_sales")

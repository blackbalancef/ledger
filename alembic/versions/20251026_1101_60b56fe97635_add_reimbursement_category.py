"""add_reimbursement_category

Revision ID: 60b56fe97635
Revises: 5be9eae5b608
Create Date: 2025-10-26 11:01:34.086369

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '60b56fe97635'
down_revision: Union[str, None] = '5be9eae5b608'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add Reimbursement category for income
    op.execute("""
        INSERT INTO categories (name, transaction_type, icon, is_default) 
        VALUES ('Reimbursement', 'INCOME', '💸', false);
    """)


def downgrade() -> None:
    # Remove Reimbursement category
    op.execute("""
        DELETE FROM categories 
        WHERE name = 'Reimbursement' AND transaction_type = 'INCOME';
    """)


"""add position_checklist_access

Revision ID: d7a24c42cd70
Revises: 593fe0153f90
Create Date: 2025-07-18 23:38:34.904112

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7a24c42cd70'
down_revision: Union[str, Sequence[str], None] = '593fe0153f90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('checklists', 'created_by',
               existing_type=sa.INTEGER(),
               nullable=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('checklists', 'created_by',
               existing_type=sa.INTEGER(),
               nullable=True)
    # ### end Alembic commands ###

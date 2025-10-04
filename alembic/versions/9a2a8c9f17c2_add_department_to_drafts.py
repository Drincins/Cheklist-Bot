"""Add department column to checklist drafts

Revision ID: 9a2a8c9f17c2
Revises: 80ec8a358277
Create Date: 2025-09-09 12:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9a2a8c9f17c2'
down_revision: Union[str, Sequence[str], None] = '80ec8a358277'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('checklist_drafts', sa.Column('department', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('checklist_drafts', 'department')

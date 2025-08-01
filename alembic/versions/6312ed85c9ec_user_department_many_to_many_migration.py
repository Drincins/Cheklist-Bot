"""user-department many-to-many migration

Revision ID: 6312ed85c9ec
Revises: 21e5d887c5a3
Create Date: 2025-08-01 22:43:40.674212

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6312ed85c9ec'
down_revision: Union[str, Sequence[str], None] = '21e5d887c5a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # 1. Удалить старое строковое поле
    op.drop_column('users', 'department')
    # 2. Создать таблицу user_department_access
    op.create_table(
        'user_department_access',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('department_id', sa.Integer(), sa.ForeignKey('departments.id', ondelete='CASCADE'), primary_key=True)
    )
def downgrade():
    op.add_column('users', sa.Column('department', sa.String(), nullable=True))
    op.drop_table('user_department_access')

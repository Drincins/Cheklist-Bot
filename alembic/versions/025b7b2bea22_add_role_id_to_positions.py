"""add role_id to positions

Revision ID: 025b7b2bea22
Revises: 6312ed85c9ec
Create Date: 2025-08-01 23:56:19.230574

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '025b7b2bea22'
down_revision: Union[str, Sequence[str], None] = '6312ed85c9ec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Добавить role_id к positions
    op.add_column('positions', sa.Column('role_id', sa.Integer(), nullable=True))
    # 2. Создать FK на roles
    op.create_foreign_key(
        'fk_positions_role',
        'positions', 'roles',
        ['role_id'], ['id']
    )
    # 3. Удалить старое поле role у пользователей
    op.drop_column('users', 'role')


def downgrade() -> None:
    # 1. Вернуть поле role в users (пример с Enum)
    op.add_column(
        'users',
        sa.Column('role', sa.Enum('employee', 'senior_admin', 'main_admin', name='user_roles'), nullable=True)
    )
    # 2. Убрать внешний ключ и колонку
    op.drop_constraint('fk_positions_role', 'positions', type_='foreignkey')
    op.drop_column('positions', 'role_id')
    # 3. roles не трогай! (таблица не твоя миграция создаёт)

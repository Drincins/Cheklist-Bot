"""f

Revision ID: e274dd0398fb
Revises: 52b4f5ac3965
Create Date: 2025-08-09 01:39:43.971279

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e274dd0398fb'
down_revision: Union[str, Sequence[str], None] = '52b4f5ac3965'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column('checklist_questions', sa.Column('weight', sa.Integer(), nullable=True))
    op.add_column('checklist_questions', sa.Column('require_photo', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('checklist_questions', sa.Column('require_comment', sa.Boolean(), server_default=sa.text('false'), nullable=False))

    # Бэкофилл из JSON meta, если уже что-то было
    op.execute("""
    UPDATE checklist_questions
    SET
        weight = NULLIF(meta->>'weight','')::int,
        require_photo = COALESCE((meta->>'require_photo')::boolean, false),
        require_comment = COALESCE((meta->>'require_comment')::boolean, false)
    WHERE meta IS NOT NULL;
    """)

    # Убираем server_default, чтобы не залип на уровне схемы
    op.alter_column('checklist_questions', 'require_photo', server_default=None)
    op.alter_column('checklist_questions', 'require_comment', server_default=None)

def downgrade():
    op.drop_column('checklist_questions', 'require_comment')
    op.drop_column('checklist_questions', 'require_photo')
    op.drop_column('checklist_questions', 'weight')
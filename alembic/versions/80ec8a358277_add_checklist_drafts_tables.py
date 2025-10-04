"""Add checklist drafts tables

Revision ID: 80ec8a358277
Revises: 65ee6bcd2fc8
Create Date: 2025-09-09 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '80ec8a358277'
down_revision: Union[str, Sequence[str], None] = '65ee6bcd2fc8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'checklist_drafts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('checklist_id', sa.Integer(), sa.ForeignKey('checklists.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_cd_user', 'checklist_drafts', ['user_id'])
    op.create_unique_constraint('uq_cd_user_checklist', 'checklist_drafts', ['user_id', 'checklist_id'])

    op.create_table(
        'checklist_draft_answers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('draft_id', sa.Integer(), sa.ForeignKey('checklist_drafts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('question_id', sa.Integer(), sa.ForeignKey('checklist_questions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('response_value', sa.String(), nullable=True),
        sa.Column('comment', sa.String(), nullable=True),
        sa.Column('photo_path', sa.String(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_cda_draft_id', 'checklist_draft_answers', ['draft_id'])
    op.create_index('ix_cda_question_id', 'checklist_draft_answers', ['question_id'])
    op.create_unique_constraint('uq_cda_draft_question', 'checklist_draft_answers', ['draft_id', 'question_id'])


def downgrade() -> None:
    op.drop_constraint('uq_cda_draft_question', 'checklist_draft_answers', type_='unique')
    op.drop_index('ix_cda_question_id', table_name='checklist_draft_answers')
    op.drop_index('ix_cda_draft_id', table_name='checklist_draft_answers')
    op.drop_table('checklist_draft_answers')

    op.drop_constraint('uq_cd_user_checklist', 'checklist_drafts', type_='unique')
    op.drop_index('ix_cd_user', table_name='checklist_drafts')
    op.drop_table('checklist_drafts')

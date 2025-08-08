"""f

Revision ID: b24ba9379e63
Revises: e274dd0398fb
Create Date: 2025-08-09 01:40:26.665966

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b24ba9379e63'
down_revision: Union[str, Sequence[str], None] = 'e274dd0398fb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_fks_on_columns(table: str, columns: list[str]):
    """Снести все FK на указанные колонки, имя не важно."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for fk in insp.get_foreign_keys(table):
        if set(fk.get("constrained_columns", [])) == set(columns) and fk.get("name"):
            op.drop_constraint(fk["name"], table_name=table, type_="foreignkey")

def upgrade():
    # ---- 1) Пересоздаём FK с ON DELETE CASCADE ----
    # checklist_question_answers.question_id -> checklist_questions.id
    _drop_fks_on_columns("checklist_question_answers", ["question_id"])
    op.create_foreign_key(
        "fk_cqa_question_id_questions",
        source_table="checklist_question_answers",
        referent_table="checklist_questions",
        local_cols=["question_id"],
        remote_cols=["id"],
        ondelete="CASCADE",
    )

    # checklist_question_answers.answer_id -> checklist_answers.id
    _drop_fks_on_columns("checklist_question_answers", ["answer_id"])
    op.create_foreign_key(
        "fk_cqa_answer_id_answers",
        source_table="checklist_question_answers",
        referent_table="checklist_answers",
        local_cols=["answer_id"],
        remote_cols=["id"],
        ondelete="CASCADE",
    )

    # checklist_answers.checklist_id -> checklists.id
    _drop_fks_on_columns("checklist_answers", ["checklist_id"])
    op.create_foreign_key(
        "fk_ca_checklist_id_checklists",
        source_table="checklist_answers",
        referent_table="checklists",
        local_cols=["checklist_id"],
        remote_cols=["id"],
        ondelete="CASCADE",
    )

    # checklist_questions.checklist_id -> checklists.id
    _drop_fks_on_columns("checklist_questions", ["checklist_id"])
    op.create_foreign_key(
        "fk_cq_checklist_id_checklists",
        source_table="checklist_questions",
        referent_table="checklists",
        local_cols=["checklist_id"],
        remote_cols=["id"],
        ondelete="CASCADE",
    )

    # ---- 2) Индексы ----
    op.create_index("ix_ca_ck_user_date", "checklist_answers", ["checklist_id", "user_id", "submitted_at"])
    op.create_index("ix_cqa_answer_id", "checklist_question_answers", ["answer_id"])
    op.create_index("ix_cqa_question_id", "checklist_question_answers", ["question_id"])
    op.create_index("ix_cqa_answer_question", "checklist_question_answers", ["answer_id", "question_id"])

def downgrade():
    # ---- откат индексов ----
    op.drop_index("ix_cqa_answer_question", table_name="checklist_question_answers")
    op.drop_index("ix_cqa_question_id", table_name="checklist_question_answers")
    op.drop_index("ix_cqa_answer_id", table_name="checklist_question_answers")
    op.drop_index("ix_ca_ck_user_date", table_name="checklist_answers")

    # ---- откат FK до "без каскада" ----
    _drop_fks_on_columns("checklist_questions", ["checklist_id"])
    op.create_foreign_key(
        "checklist_questions_checklist_id_fkey",
        "checklist_questions",
        "checklists",
        ["checklist_id"],
        ["id"],
    )

    _drop_fks_on_columns("checklist_answers", ["checklist_id"])
    op.create_foreign_key(
        "checklist_answers_checklist_id_fkey",
        "checklist_answers",
        "checklists",
        ["checklist_id"],
        ["id"],
    )

    _drop_fks_on_columns("checklist_question_answers", ["answer_id"])
    op.create_foreign_key(
        "checklist_question_answers_answer_id_fkey",
        "checklist_question_answers",
        "checklist_answers",
        ["answer_id"],
        ["id"],
    )

    _drop_fks_on_columns("checklist_question_answers", ["question_id"])
    op.create_foreign_key(
        "checklist_question_answers_question_id_fkey",
        "checklist_question_answers",
        "checklist_questions",
        ["question_id"],
        ["id"],
    )
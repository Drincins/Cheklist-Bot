"""repair sections & drafts (idempotent)

Revision ID: repair_sections_safe
Revises: 65ee6bcd2fc8
Create Date: 2025-09-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.sql import text


# ревизии
revision = "repair_sections_safe"
down_revision = "65ee6bcd2fc8"
branch_labels = None
depends_on = None


def _table_exists(conn, name: str) -> bool:
    insp = inspect(conn)
    return name in insp.get_table_names()


def _column_exists(conn, table: str, column: str) -> bool:
    insp = inspect(conn)
    cols = {c["name"] for c in insp.get_columns(table)}
    return column in cols


def _index_exists(conn, table: str, index: str) -> bool:
    insp = inspect(conn)
    idxs = {i["name"] for i in insp.get_indexes(table)}
    return index in idxs


def _fk_exists(conn, table: str, fk_name: str) -> bool:
    insp = inspect(conn)
    fks = {fk["name"] for fk in insp.get_foreign_keys(table)}
    return fk_name in fks


def upgrade():
    conn = op.get_bind()

    # 1) checklist_sections (создать, если нет)
    if not _table_exists(conn, "checklist_sections"):
        op.create_table(
            "checklist_sections",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("checklist_id", sa.Integer(), sa.ForeignKey("checklists.id", ondelete="CASCADE"), index=True, nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("order", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )
        if not _index_exists(conn, "checklist_sections", "ix_checklist_sections_ck_order"):
            op.create_index("ix_checklist_sections_ck_order", "checklist_sections", ["checklist_id", "order"])

    # 2) checklist_questions: section_id + индексы/FK (если нет)
    if not _column_exists(conn, "checklist_questions", "section_id"):
        op.add_column("checklist_questions", sa.Column("section_id", sa.Integer(), nullable=True))
    if not _index_exists(conn, "checklist_questions", "ix_cq_section_id_order"):
        op.create_index("ix_cq_section_id_order", "checklist_questions", ["section_id", "order"])
    if not _fk_exists(conn, "checklist_questions", "fk_cq_section_id"):
        op.create_foreign_key(
            "fk_cq_section_id",
            "checklist_questions",
            "checklist_sections",
            ["section_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # 3) checklist_answers: started_at, is_submitted, current_section_id (мягко)
    if not _column_exists(conn, "checklist_answers", "started_at"):
        op.add_column("checklist_answers", sa.Column("started_at", sa.DateTime(), nullable=True, server_default=sa.text("now()")))
    if not _column_exists(conn, "checklist_answers", "is_submitted"):
        op.add_column("checklist_answers", sa.Column("is_submitted", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    if not _column_exists(conn, "checklist_answers", "current_section_id"):
        op.add_column("checklist_answers", sa.Column("current_section_id", sa.Integer(), nullable=True))
    if not _fk_exists(conn, "checklist_answers", "fk_ca_current_section_id"):
        op.create_foreign_key(
            "fk_ca_current_section_id",
            "checklist_answers",
            "checklist_sections",
            ["current_section_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if not _index_exists(conn, "checklist_answers", "ix_ca_ck_user_started"):
        op.create_index("ix_ca_ck_user_started", "checklist_answers", ["checklist_id", "user_id", "started_at"])

    # 3.1 BACKFILL: проставим started_at / is_submitted
    conn.execute(text("""
        UPDATE checklist_answers
        SET
            started_at = COALESCE(started_at, COALESCE(submitted_at, now())),
            is_submitted = COALESCE(is_submitted, CASE WHEN submitted_at IS NOT NULL THEN TRUE ELSE FALSE END)
    """))

    # 3.2 Ужесточим started_at -> NOT NULL (если колонка существует)
    with op.batch_alter_table("checklist_answers") as batch_op:
        batch_op.alter_column(
            "started_at",
            existing_type=sa.DateTime(),
            nullable=False,
            existing_nullable=True,
            server_default=None,
        )

    # 4) checklist_questions.required -> NOT NULL DEFAULT TRUE (мягко)
    conn.execute(text("UPDATE checklist_questions SET required = TRUE WHERE required IS NULL"))
    with op.batch_alter_table("checklist_questions") as batch_op:
        batch_op.alter_column(
            "required",
            existing_type=sa.Boolean(),
            nullable=False,
            existing_nullable=True,
            server_default=sa.text("true"),
        )

    # 5) BACKFILL стандартных разделов и связка вопросов
    #    Для каждого чек-листа добавим 'Общий раздел', если для него нет ни одного раздела,
    #    и привяжем вопросы без section_id.
    ck_ids = [row[0] for row in conn.execute(text("SELECT id FROM checklists")).fetchall()]
    for ck_id in ck_ids:
        # Есть ли уже разделы для этого чек-листа?
        has_sections = conn.execute(
            text("SELECT 1 FROM checklist_sections WHERE checklist_id=:cid LIMIT 1"),
            {"cid": ck_id}
        ).fetchone() is not None

        if not has_sections:
            sec_id = conn.execute(
                text("""
                    INSERT INTO checklist_sections (checklist_id, title, description, "order", is_required)
                    VALUES (:cid, 'Общий раздел', NULL, 1, FALSE)
                    RETURNING id
                """),
                {"cid": ck_id}
            ).scalar()
        else:
            # возьмём любой существующий раздел для привязки, если понадобится
            sec_id = conn.execute(
                text("SELECT id FROM checklist_sections WHERE checklist_id=:cid ORDER BY \"order\" LIMIT 1"),
                {"cid": ck_id}
            ).scalar()

        # привяжем вопросы без section_id
        conn.execute(
            text("""
                UPDATE checklist_questions
                SET section_id = :sid
                WHERE checklist_id = :cid AND section_id IS NULL
            """),
            {"sid": sec_id, "cid": ck_id}
        )

    # 5.2 Сделаем section_id NOT NULL (теперь безопасно)
    with op.batch_alter_table("checklist_questions") as batch_op:
        batch_op.alter_column(
            "section_id",
            existing_type=sa.Integer(),
            nullable=False,
            existing_nullable=True,
        )


def downgrade():
    # максимально мягкий откат
    conn = op.get_bind()

    # checklist_answers
    if _index_exists(conn, "checklist_answers", "ix_ca_ck_user_started"):
        op.drop_index("ix_ca_ck_user_started", table_name="checklist_answers")
    if _fk_exists(conn, "checklist_answers", "fk_ca_current_section_id"):
        op.drop_constraint("fk_ca_current_section_id", "checklist_answers", type_="foreignkey")
    if _column_exists(conn, "checklist_answers", "current_section_id"):
        op.drop_column("checklist_answers", "current_section_id")
    if _column_exists(conn, "checklist_answers", "is_submitted"):
        op.drop_column("checklist_answers", "is_submitted")
    if _column_exists(conn, "checklist_answers", "started_at"):
        op.drop_column("checklist_answers", "started_at")

    # checklist_questions
    with op.batch_alter_table("checklist_questions") as batch_op:
        batch_op.alter_column(
            "required",
            existing_type=sa.Boolean(),
            nullable=True,
            existing_nullable=False,
            server_default=None,
        )
    if _fk_exists(conn, "checklist_questions", "fk_cq_section_id"):
        op.drop_constraint("fk_cq_section_id", "checklist_questions", type_="foreignkey")
    if _index_exists(conn, "checklist_questions", "ix_cq_section_id_order"):
        op.drop_index("ix_cq_section_id_order", table_name="checklist_questions")
    if _column_exists(conn, "checklist_questions", "section_id"):
        op.drop_column("checklist_questions", "section_id")

    # checklist_sections
    if _index_exists(conn, "checklist_sections", "ix_checklist_sections_ck_order"):
        op.drop_index("ix_checklist_sections_ck_order", table_name="checklist_sections")
    if _table_exists(conn, "checklist_sections"):
        op.drop_table("checklist_sections")

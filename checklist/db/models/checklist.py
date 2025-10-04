from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, DateTime, JSON, Table, Index, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from checklist.db.base import Base
from checklist.db.models.role import position_checklist_access



class Checklist(Base):
    __tablename__ = "checklists"


    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    is_scored = Column(Boolean, default=False)
    created_by = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Доступ чек-листа по должностям
    positions = relationship(
        "Position",
        secondary=position_checklist_access,
        back_populates="checklists",
        back_populates="checklists",
    )

    # Разделы чек-листа (новое)
    sections = relationship(
        "ChecklistSection",
        back_populates="checklist",
        order_by="ChecklistSection.order",
        cascade="all, delete-orphan",
    )


class ChecklistSection(Base):
    """
    Раздел чек-листа.
    Один чек-лист -> много разделов.
    """
    __tablename__ = "checklist_sections"

    id = Column(Integer, primary_key=True)
    checklist_id = Column(Integer, ForeignKey("checklists.id", ondelete="CASCADE"), index=True, nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    order = Column(Integer, nullable=False, default=1)     # порядок раздела внутри чек-листа
    is_required = Column(Boolean, nullable=False, default=False)

    checklist = relationship("Checklist", back_populates="sections")
    questions = relationship(
        "ChecklistQuestion",
        back_populates="section",
        order_by="ChecklistQuestion.order",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_checklist_sections_ck_order", "checklist_id", "order"),
    )


class ChecklistQuestion(Base):
    __tablename__ = "checklist_questions"


    id = Column(Integer, primary_key=True)
    checklist_id = Column(Integer, ForeignKey("checklists.id", ondelete="CASCADE"), nullable=False)

    # Порядок вопроса внутри раздела/чек-листа
    order = Column(Integer, nullable=False)

    # Привязка к разделу (новое). Может быть NULL для «несекционированных» старых вопросов
    section_id = Column(Integer, ForeignKey("checklist_sections.id", ondelete="SET NULL"), index=True, nullable=True)

    text = Column(String, nullable=False)
    type = Column(String, nullable=False)  # yesno, scale, short_text, long_text
    required = Column(Boolean, nullable=False, default=True)  # запретим NULL и оставим дефолт True
    meta = Column(JSON, nullable=True)     # доп. настройки (например, min/max для шкалы)
    weight = Column(Integer, nullable=True)                  # вес вопроса (для оцениваемых чек-листов)
    require_photo = Column(Boolean, default=False, nullable=False)   # обяз. фото
    require_comment = Column(Boolean, default=False, nullable=False) # обяз. комментарий

    # связь с разделом (новое)
    section = relationship("ChecklistSection", back_populates="questions")

    __table_args__ = (
        Index("ix_cq_checklist_id_order", "checklist_id", "order"),
        Index("ix_cq_section_id_order", "section_id", "order"),
    )


class ChecklistAnswer(Base):
    """
    Шапка ответа (прохождение чек-листа).
    Раньше считалась финальной отправкой. Теперь поддерживает черновик:
      - started_at   — когда начали;
      - is_submitted — флаг финальной отправки;
      - current_section_id — текущий раздел для продолжения.
    """
    __tablename__ = "checklist_answers"


    id = Column(Integer, primary_key=True)
    checklist_id = Column(Integer, ForeignKey("checklists.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Черновик/прохождение
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_submitted = Column(Boolean, default=False, nullable=False)

    # Для навигации по разделам в UI
    current_section_id = Column(Integer, ForeignKey("checklist_sections.id", ondelete="SET NULL"), nullable=True)

    # Момент финальной отправки (для уже отправленных)
    submitted_at = Column(DateTime, default=None, nullable=True)

    __table_args__ = (
        Index("ix_ca_ck_user_date", "checklist_id", "user_id", "submitted_at"),
        Index("ix_ca_ck_user_started", "checklist_id", "user_id", "started_at"),
    )

    # (опционально) связь с разделом, если хочешь быстро тянуть current_section
    current_section = relationship("ChecklistSection", foreign_keys=[current_section_id])


class ChecklistQuestionAnswer(Base):
    __tablename__ = "checklist_question_answers"


    id = Column(Integer, primary_key=True)
    answer_id = Column(Integer, ForeignKey("checklist_answers.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(Integer, ForeignKey("checklist_questions.id", ondelete="CASCADE"), nullable=False)

    response_value = Column(String, nullable=True)   # Основной ответ (Да/Нет/число/текст)
    comment = Column(String, nullable=True)          # Комментарий пользователя
    photo_path = Column(String, nullable=True)       # file_id из Telegram или путь к фото
    created_at = Column(DateTime, default=datetime.utcnow)


    __table_args__ = (
        Index("ix_cqa_answer_id", "answer_id"),
        Index("ix_cqa_question_id", "question_id"),
        Index("ix_cqa_answer_question", "answer_id", "question_id"),
    )

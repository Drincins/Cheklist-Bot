from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, DateTime, JSON, Table, Index
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
    positions = relationship(
        "Position",
        secondary=position_checklist_access,
        back_populates="checklists"
    )

class ChecklistQuestion(Base):
    __tablename__ = "checklist_questions"
    id = Column(Integer, primary_key=True)
    checklist_id = Column(Integer, ForeignKey("checklists.id", ondelete="CASCADE"), nullable=False)
    order = Column(Integer, nullable=False)
    text = Column(String, nullable=False)
    type = Column(String, nullable=False)  # yesno, scale, short_text, long_text
    required = Column(Boolean, default=True)
    meta = Column(JSON, nullable=True)     # доп. настройки (например, min/max для шкалы)
    weight = Column(Integer, nullable=True)                  # вес вопроса (для оцениваемых чек-листов)
    require_photo = Column(Boolean, default=False, nullable=False)   # обяз. фото
    require_comment = Column(Boolean, default=False, nullable=False) # обяз. комментарий

class ChecklistAnswer(Base):
    __tablename__ = "checklist_answers"
    id = Column(Integer, primary_key=True)
    checklist_id = Column(Integer, ForeignKey("checklists.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    submitted_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (
        Index("ix_ca_ck_user_date", "checklist_id", "user_id", "submitted_at"),
    )

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

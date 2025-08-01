from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, DateTime, JSON, Table
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
    checklist_id = Column(Integer, ForeignKey("checklists.id"), nullable=False)
    order = Column(Integer, nullable=False)
    text = Column(String, nullable=False)
    type = Column(String, nullable=False)  # yesno, scale, short_text, long_text
    required = Column(Boolean, default=True)
    meta = Column(JSON, nullable=True)     # доп. настройки (например, min/max для шкалы)

class ChecklistAnswer(Base):
    __tablename__ = "checklist_answers"
    id = Column(Integer, primary_key=True)
    checklist_id = Column(Integer, ForeignKey("checklists.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    submitted_at = Column(DateTime, default=datetime.utcnow)

class ChecklistQuestionAnswer(Base):
    __tablename__ = "checklist_question_answers"
    id = Column(Integer, primary_key=True)
    answer_id = Column(Integer, ForeignKey("checklist_answers.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("checklist_questions.id"), nullable=False)
    response_value = Column(String, nullable=True)   # Основной ответ (Да/Нет/число/текст)
    comment = Column(String, nullable=True)          # Комментарий пользователя
    photo_path = Column(String, nullable=True)       # file_id из Telegram или путь к фото
    created_at = Column(DateTime, default=datetime.utcnow)

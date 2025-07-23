from sqlalchemy import (
    Table, Column, Integer, String, ForeignKey, Enum,
    Boolean, DateTime, JSON
)
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

position_checklist_access = Table(
    "position_checklist_access", Base.metadata,
    Column("position_id", Integer, ForeignKey("positions.id", ondelete="CASCADE"), primary_key=True),
    Column("checklist_id", Integer, ForeignKey("checklists.id", ondelete="CASCADE"), primary_key=True)
)
# ——— Компания
class Company(Base):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)

# ——— Чек-лист (основная сущность)
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

# ——— Должности внутри компании
class Position(Base):
    __tablename__ = "positions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    checklists = relationship(
        "Checklist",
        secondary=position_checklist_access,
        back_populates="positions"
    )    
# ——— Пользователи компании
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    telegram_id = Column(Integer, unique=True, nullable=True)
    phone = Column(String, nullable=True)
    role = Column(Enum("employee", "senior_admin", "main_admin", name="user_roles"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    position_id = Column(Integer, ForeignKey("positions.id"), nullable=True)
    login = Column(String, unique=True, nullable=True)
    hashed_password = Column(String, nullable=True)
    
    position = relationship("Position", backref="users")
# ——— Вопрос чек-листа
class ChecklistQuestion(Base):
    __tablename__ = "checklist_questions"
    id = Column(Integer, primary_key=True)
    checklist_id = Column(Integer, ForeignKey("checklists.id"), nullable=False)
    order = Column(Integer, nullable=False)
    text = Column(String, nullable=False)
    type = Column(String, nullable=False)  # yesno, scale, short_text, long_text
    required = Column(Boolean, default=True)
    meta = Column(JSON, nullable=True)     # доп. настройки (например, min/max для шкалы)

# ——— Ответ пользователя на чек-лист (одна "сессия" прохождения)
class ChecklistAnswer(Base):
    __tablename__ = "checklist_answers"
    id = Column(Integer, primary_key=True)
    checklist_id = Column(Integer, ForeignKey("checklists.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    submitted_at = Column(DateTime, default=datetime.utcnow)

# ——— Ответ пользователя на вопрос чек-листа
class ChecklistQuestionAnswer(Base):
    __tablename__ = "checklist_question_answers"
    id = Column(Integer, primary_key=True)
    answer_id = Column(Integer, ForeignKey("checklist_answers.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("checklist_questions.id"), nullable=False)
    response_value = Column(String, nullable=True)   # Основной ответ (Да/Нет/число/текст)
    comment = Column(String, nullable=True)          # Комментарий пользователя
    photo_path = Column(String, nullable=True)       # file_id из Telegram или путь к фото
    created_at = Column(DateTime, default=datetime.utcnow)

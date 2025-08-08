# bot/bot_db.py

import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session  # <-- Важно: импортируем Session

from dotenv import load_dotenv

from checklist.db.base import Base
from checklist.db.models import (
    Company,
    Department,
    Role,
    Position,
    Checklist,
    ChecklistQuestion,
    ChecklistAnswer,
    ChecklistQuestionAnswer,
    User,
)

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL не задан. Создай .env и добавь строку подключения, например:\n"
        "DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/checklist_db"
    )

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    """Локальная инициализация схемы (для dev). На проде — Alembic."""
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_db() -> Iterator[Session]:  # <-- Правильная аннотация
    """
    Контекстный менеджер для работы с БД:
        with get_db() as db:
            ...
    """
    db: Session = SessionLocal()  # <-- Подсказываем тип явным образом
    try:
        yield db
        # Коммит оставляем на усмотрение вызывающего кода
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


__all__ = [
    "engine",
    "SessionLocal",
    "get_db",
    "init_db",
    "Base",
    "Company",
    "Department",
    "Role",
    "Position",
    "Checklist",
    "ChecklistQuestion",
    "ChecklistAnswer",
    "ChecklistQuestionAnswer",
    "User",
]

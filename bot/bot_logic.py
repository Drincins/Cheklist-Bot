import os
import re
from datetime import datetime
from typing import Optional, List, Dict

from sqlalchemy import func
from sqlalchemy.orm import joinedload

# чтобы импортировать пакет checklist из соседней директории
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Берём SessionLocal из новой структуры
from checklist.db.db import SessionLocal

# Модели лежат в checklist/db/models
from checklist.db.models import (
    Company,
    Department,
    User,
    Role,
    Position,
    Checklist,
    ChecklistQuestion,
    ChecklistAnswer,
    ChecklistQuestionAnswer,
)


# ──────────────────────────────────────────────────────────────────────────────
# Утилиты
# ──────────────────────────────────────────────────────────────────────────────
def normalize_phone(phone: str) -> str:
    """Оставляем только цифры и берём последние 10."""
    digits = re.sub(r"\D", "", phone or "")
    return digits[-10:] if len(digits) >= 10 else digits


# ──────────────────────────────────────────────────────────────────────────────
# Авторизация
# ──────────────────────────────────────────────────────────────────────────────
def find_user_by_name_phone_company(name: str, phone: str, company_name: Optional[str] = None) -> Optional[Dict]:
    clean = normalize_phone(phone)
    if not clean:
        return None

    with SessionLocal() as db:
        q = (
            db.query(User, Company.name.label("company_name"))
            .join(Company, User.company_id == Company.id)
            .outerjoin(Position, User.position_id == Position.id)
            .options(
                joinedload(User.position).joinedload(Position.role),
                joinedload(User.departments),
            )
            .filter(
                func.lower(User.name) == (name or "").strip().lower(),
                func.right(User.phone, len(clean)) == clean,
            )
        )
        if company_name:
            q = q.filter(Company.name == company_name.strip())

        res = q.first()
        if not res:
            print(f"[AUTH] Not found: name='{name}', phone_ending='{clean}', company='{company_name}'")
            return None

        user, comp = res
        return {
            "id": user.id,
            "name": user.name,
            "phone": user.phone,
            "company_id": user.company_id,
            "company_name": comp,
            "position": user.position.name if user.position else "Не указано",
            "departments": [d.name for d in (user.departments or [])],
        }


# ──────────────────────────────────────────────────────────────────────────────
# Чек‑листы (доступные пользователю)
# ──────────────────────────────────────────────────────────────────────────────
def get_checklists_for_user(user_id: int, page: int = 0, page_size: int = 8) -> List[Dict]:
    """
    Возвращает список чек-листов пользователя:
    [{"id": 1, "name": "Открытие смены"}, ...]
    Берём через Position ↔ Checklist (M2M).
    """
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if not user or not user.position:
            return []

        all_cls = user.position.checklists
        start = page * page_size
        end = start + page_size
        sliced = all_cls[start:end]
        return [{"id": c.id, "name": c.name} for c in sliced]


def count_checklists_for_user(user_id: int) -> int:
    with SessionLocal() as db:
        user = db.get(User, user_id)
        return len(user.position.checklists) if user and user.position else 0


# ──────────────────────────────────────────────────────────────────────────────
# Вопросы чек‑листа
# ──────────────────────────────────────────────────────────────────────────────
def get_questions_for_checklist(checklist_id: int) -> List[Dict]:
    """
    [{"id","text","type","order","meta"}, ...]
    """
    with SessionLocal() as db:
        questions = (
            db.query(ChecklistQuestion)
            .filter(ChecklistQuestion.checklist_id == checklist_id)
            .order_by(ChecklistQuestion.order)
            .all()
        )
        return [
            {
                "id": q.id,
                "text": q.text,
                "type": q.type,
                "order": q.order,
                "meta": q.meta,
            }
            for q in questions
        ]


# ──────────────────────────────────────────────────────────────────────────────
# Сохранение результатов
# ──────────────────────────────────────────────────────────────────────────────
def save_checklist_with_answers(user_id: int, checklist_id: int, answers: List[Dict]) -> None:
    """
    answers: список словарей:
    {
        "question_id": int,
        "response_value": str|None,
        "comment": str|None,
        "photo_path": str|None
    }
    """
    with SessionLocal() as db:
        session = ChecklistAnswer(
            user_id=user_id,
            checklist_id=checklist_id,
            submitted_at=datetime.utcnow(),
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        for ans in answers:
            db.add(
                ChecklistQuestionAnswer(
                    answer_id=session.id,      # FK на ChecklistAnswer
                    question_id=ans["question_id"],
                    response_value=ans.get("response_value"),
                    comment=ans.get("comment"),
                    photo_path=ans.get("photo_path"),
                    created_at=datetime.utcnow(),
                )
            )

        db.commit()


# ──────────────────────────────────────────────────────────────────────────────
# Служебные методы
# ──────────────────────────────────────────────────────────────────────────────
def get_checklist_by_id(checklist_id: int) -> Optional[Checklist]:
    with SessionLocal() as db:
        return db.get(Checklist, checklist_id)


def get_completed_checklists_for_user(user_id: int) -> List[Dict]:
    """Возвращает последние прохождения по каждому чек‑листу (имя + дата)."""
    with SessionLocal() as db:
        rows = (
            db.query(Checklist.name, ChecklistAnswer.submitted_at)
            .join(Checklist, Checklist.id == ChecklistAnswer.checklist_id)
            .filter(ChecklistAnswer.user_id == user_id)
            .order_by(ChecklistAnswer.submitted_at.desc())
            .all()
        )
        seen = {}
        for name, ts in rows:
            if name not in seen:
                seen[name] = ts
        return [{"name": k, "completed_at": v} for k, v in seen.items()]

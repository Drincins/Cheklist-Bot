import os
import re
from datetime import datetime
from typing import Optional, List, Dict

from sqlalchemy import func
from sqlalchemy.orm import joinedload

# абсолютные импорты из соседнего пакета checklist
from checklist.db.models.checklist import (
    Checklist, ChecklistAnswer, ChecklistQuestion, ChecklistQuestionAnswer
)
from checklist.db.models.user import User

# Берём SessionLocal из новой структуры
from checklist.db.db import SessionLocal

# Модели лежат в checklist/db/models
from checklist.db.models import (
    Company,
    Department,
    User as UserModel,   # чтобы не затереть импорт User выше (если не используешь — можешь убрать)
    Role,
    Position,
    Checklist as ChecklistModel,
    ChecklistQuestion as ChecklistQuestionModel,
    ChecklistAnswer as ChecklistAnswerModel,
    ChecklistQuestionAnswer as ChecklistQuestionAnswerModel,
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
# Пройденные чек-листы (пагинация + данные для отчёта)
# ──────────────────────────────────────────────────────────────────────────────

def get_completed_answers_paginated(user_id: int, offset: int = 0, limit: int = 8):
    """
    Возвращает:
      items: список словарей [{"answer_id", "checklist_name", "submitted_at"}]
      total: общее количество прохождений пользователя
    """
    with SessionLocal() as db:
        base_q = (
            db.query(ChecklistAnswer.id, Checklist.name, ChecklistAnswer.submitted_at)
            .join(Checklist, Checklist.id == ChecklistAnswer.checklist_id)
            .filter(ChecklistAnswer.user_id == user_id)
            .order_by(ChecklistAnswer.submitted_at.desc())
        )
        total = base_q.count()
        rows = base_q.offset(offset).limit(limit).all()
        items = [
            {"answer_id": r[0], "checklist_name": r[1], "submitted_at": r[2]}
            for r in rows
        ]
        return items, total


def get_answer_report_data(answer_id: int):
    """
    Возвращает словарь с полями для отчёта:
      {
        "checklist_name", "date", "time", "department", "result" (или None)
      }
    - department берём из департаментов пользователя
    - result: если чек-лист помечен как is_scored, считаем:
        • для yesno — % ответов «да»
        • для scale — % среднего значения от максимума (meta.max, по умолчанию 10)
      Если посчитать нечего — None
    """
    with SessionLocal() as db:
        ans = db.get(ChecklistAnswer, answer_id)
        if not ans:
            return None

        checklist = db.get(Checklist, ans.checklist_id)
        user = db.get(User, ans.user_id)

        # департаменты пользователя
        departments = [d.name for d in (user.departments or [])] if user else []
        department = ", ".join(departments) if departments else "—"

        # базовые поля
        date_str = ans.submitted_at.strftime("%d.%m.%Y")
        time_str = ans.submitted_at.strftime("%H:%M")
        checklist_name = checklist.name if checklist else "—"

        # расчёт результата (если is_scored)
        result = None
        if checklist and getattr(checklist, "is_scored", False):
            rows = (
                db.query(
                    ChecklistQuestion.type,
                    ChecklistQuestion.meta,
                    ChecklistQuestionAnswer.response_value,
                )
                .join(ChecklistQuestion, ChecklistQuestion.id == ChecklistQuestionAnswer.question_id)
                .filter(ChecklistQuestionAnswer.answer_id == answer_id)
                .all()
            )

            yes_cnt = 0
            yes_total = 0
            scale_sum = 0.0
            scale_cnt = 0.0

            for qtype, meta, resp in rows:
                if qtype == "yesno":
                    yes_total += 1
                    if resp and str(resp).strip().lower() in ("да", "yes", "true", "1"):
                        yes_cnt += 1
                elif qtype == "scale":
                    try:
                        val = float(resp)
                        mx = float((meta or {}).get("max", 10))
                        if mx > 0:
                            scale_sum += (val / mx)
                            scale_cnt += 1.0
                    except Exception:
                        pass

            parts = []
            if yes_total > 0:
                parts.append(f"{round(100 * yes_cnt / yes_total)}% «да»")
            if scale_cnt > 0:
                parts.append(f"{round(100 * (scale_sum / scale_cnt))}% шкала")
            if parts:
                result = " / ".join(parts)

        return {
            "checklist_name": checklist_name,
            "date": date_str,
            "time": time_str,
            "department": department,
            "result": result,
        }

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

# В КОНЕЦ bot/bot_logic.py добавь:

from dataclasses import dataclass
from typing import Optional, List
import datetime as dt

from checklist.db.db import SessionLocal
from checklist.db.models.checklist import (
    Checklist, ChecklistAnswer, ChecklistQuestion, ChecklistQuestionAnswer
)
from checklist.db.models.user import User
from checklist.db.models.company import Company

# Эти dataclass используются экспортом
@dataclass
class AnswerRow:
    number: int
    question: str
    qtype: str
    answer: str
    comment: Optional[str] = None
    score: Optional[float] = None      # набранный балл
    weight: Optional[float] = None     # максимальный вес (из meta)
    photo_path: Optional[str] = None

@dataclass
class AttemptData:
    attempt_id: int
    checklist_name: str
    user_name: str
    company_name: Optional[str]
    submitted_at: dt.datetime
    answers: List[AnswerRow]

def get_attempt_data(attempt_id: int) -> AttemptData:
    """
    Собирает данные одной попытки (ChecklistAnswer + его ChecklistQuestionAnswer)
    в нормализованный формат AttemptData для экспорта.
    """
    with SessionLocal() as db:
        # 1) саму попытку
        attempt: ChecklistAnswer = (
            db.query(ChecklistAnswer)
            .filter(ChecklistAnswer.id == attempt_id)
            .one()
        )

        # 2) подтягиваем имя чек-листа, сотрудника, компании
        checklist_name = db.query(Checklist.name).filter(Checklist.id == attempt.checklist_id).scalar() or f"Checklist #{attempt.checklist_id}"
        user_row = db.query(User.name, User.company_id).filter(User.id == attempt.user_id).first()
        user_name = user_row.name if user_row else "Неизвестный сотрудник"
        company_name = None
        if user_row and user_row.company_id:
            company_name = db.query(Company.name).filter(Company.id == user_row.company_id).scalar()

        submitted_at = attempt.submitted_at or dt.datetime.utcnow()

        # 3) вытаскиваем ВСЕ вопросы этого чек-листа, чтобы сохранить порядок (order)
        q_sub = (
        db.query(
            ChecklistQuestion.id,
            ChecklistQuestion.text,
            ChecklistQuestion.type,
            ChecklistQuestion.order,
            ChecklistQuestion.meta,            # ⬅️ ДОБАВИЛИ
        )
        .filter(ChecklistQuestion.checklist_id == attempt.checklist_id)
        .subquery()
    )


        # 4) вытаскиваем ответы по этой попытке и джойним на вопросы
        #    Ответ может отсутствовать на некоторый вопрос — тогда покажем пусто.
        rows = []
        q_and_a = (
        db.query(
            q_sub.c.id.label("qid"),
            q_sub.c.text.label("qtext"),
            q_sub.c.type.label("qtype"),
            q_sub.c.order.label("qorder"),
            q_sub.c.meta.label("qmeta"),                 # ⬅️ ДОБАВИЛИ
            ChecklistQuestionAnswer.response_value,
            ChecklistQuestionAnswer.comment,
            ChecklistQuestionAnswer.photo_path,
        )
        .outerjoin(
            ChecklistQuestionAnswer,
            (ChecklistQuestionAnswer.question_id == q_sub.c.id) &
            (ChecklistQuestionAnswer.answer_id == attempt_id)
        )
        .order_by(q_sub.c.order.asc())
        .all()
    )

        for idx, row in enumerate(q_and_a, start=1):
            answer_raw = row.response_value
            answer_str = str(answer_raw) if answer_raw is not None else ""

            # --- вытащим вес и параметры шкалы из meta ---
            meta = row.qmeta or {}
            weight = None
            scale_max = None
            if isinstance(meta, dict):
                weight = meta.get("weight") or meta.get("score_weight") or meta.get("points")
                scale_max = meta.get("max") or meta.get("scale_max")
                # если нет max, но есть options (список значений шкалы)
                if not scale_max and isinstance(meta.get("options"), (list, tuple)):
                    scale_max = len(meta["options"])

            # приведение типов
            try:
                if weight is not None:
                    weight = float(weight)
            except Exception:
                weight = None

            try:
                if scale_max is not None:
                    scale_max = float(scale_max)
            except Exception:
                scale_max = None

            # --- вычислим набранный балл (score) по типу вопроса ---
            qtype = (row.qtype or "").lower().strip()
            score = None

            if weight is not None:
                if qtype in {"yesno", "boolean", "bool", "yn"}:
                    s = answer_str.strip().lower()
                    if s in {"yes", "да", "true", "1"}:
                        score = weight
                    else:
                        # "no"/"нет"/"false"/"0"/пусто
                        score = 0.0

                elif qtype in {"scale", "rating"}:
                    try:
                        val = float(answer_str) if answer_str.strip() != "" else 0.0
                    except Exception:
                        val = 0.0
                    mx = scale_max if (scale_max and scale_max > 0) else 10.0
                    score = weight * (val / mx)

                else:
                    # для прочих типов обычно не считаем; оставим пусто
                    score = None

            rows.append(AnswerRow(
                number=idx,
                question=row.qtext,
                qtype=row.qtype,
                answer=answer_str,
                comment=row.comment,
                score=score,          # набранный балл
                weight=weight,        # максимальный вес
                photo_path=row.photo_path
            ))



        return AttemptData(
            attempt_id=attempt_id,
            checklist_name=checklist_name,
            user_name=user_name,
            company_name=company_name,
            submitted_at=submitted_at,
            answers=rows
        )

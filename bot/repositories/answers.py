# bot/repositories/answers.py
from __future__ import annotations
from typing import Any, Dict, Tuple, List

from sqlalchemy import func
from checklist.db.db import SessionLocal
from checklist.db.models.checklist import (
    Checklist, ChecklistAnswer, ChecklistQuestion, ChecklistQuestionAnswer
)
from checklist.db.models.user import User
from checklist.db.models.company import Department

from ..report_data import get_attempt_data  # подробные данные для экспорта

class AnswersRepo:
    def get_completed_paginated(self, user_id: int, offset: int, limit: int) -> Tuple[List[Dict[str, Any]], int]:
        """
        Возвращает (items, total), где items = [{answer_id, checklist_name, submitted_at}, ...]
        """
        with SessionLocal() as db:
            base = (
                db.query(
                    ChecklistAnswer.id.label("answer_id"),
                    Checklist.name.label("checklist_name"),
                    ChecklistAnswer.submitted_at.label("submitted_at"),
                )
                .join(Checklist, Checklist.id == ChecklistAnswer.checklist_id)
                .filter(ChecklistAnswer.user_id == user_id)
                .order_by(ChecklistAnswer.submitted_at.desc())
            )

            total = db.query(func.count(ChecklistAnswer.id)).filter(
                ChecklistAnswer.user_id == user_id
            ).scalar() or 0

            rows = base.offset(offset).limit(limit).all()
            items = [
                {
                    "answer_id": r.answer_id,
                    "checklist_name": r.checklist_name,
                    "submitted_at": r.submitted_at,
                }
                for r in rows
            ]
            return items, int(total)

    def get_report_preview(self, answer_id: int) -> Dict[str, Any] | None:
        """
        Короткая «шапка» для предпросмотра: название, дата/время, подразделение, (опционально) result.
        """
        with SessionLocal() as db:
            ans: ChecklistAnswer | None = db.query(ChecklistAnswer).get(answer_id)  # type: ignore[arg-type]
            if not ans:
                return None

            checklist: Checklist | None = db.query(Checklist).get(ans.checklist_id)  # type: ignore[arg-type]
            user: User | None = db.query(User).get(ans.user_id)  # type: ignore[arg-type]
            if not checklist or not user:
                return None

            # подразделение — список отделов пользователя
            departments = ", ".join(d.name for d in (user.departments or [])) or "—"

            # (опционально) быстрый результат: доля «Да» по yes/no
            # если чек-лист оцениваемый — считаем процент «Да»
            result: str | None = None
            try:
                if checklist.is_scored:
                    q = (
                        db.query(ChecklistQuestion.type, ChecklistQuestionAnswer.response_value)
                        .join(ChecklistQuestion, ChecklistQuestion.id == ChecklistQuestionAnswer.question_id)
                        .filter(ChecklistQuestionAnswer.answer_id == answer_id)
                    )
                    total_yesno = 0
                    yes = 0
                    for qt, resp in q.all():
                        if qt == "yesno":
                            total_yesno += 1
                            if resp and str(resp).strip().lower() in ("да", "yes", "true", "1"):
                                yes += 1
                    if total_yesno > 0:
                        result = f"{round(yes / total_yesno * 100)}%"
            except Exception:
                # если что-то пошло не так — просто не показываем result
                result = None

            dt = ans.submitted_at
            return {
                "checklist_name": checklist.name,
                "date": dt.strftime("%d.%m.%Y"),
                "time": dt.strftime("%H:%M"),
                "department": departments,
                "result": result,
            }

    def get_attempt(self, answer_id: int):
        """
        Полные данные попытки для экспорта (dataclass AttemptData) — используем готовую логику.
        """
        return get_attempt_data(answer_id)

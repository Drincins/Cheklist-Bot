# bot/repositories/answers.py
from __future__ import annotations
from typing import Any, Dict, Tuple, List

import logging

from sqlalchemy import func
from checklist.db.db import SessionLocal
from checklist.db.models.checklist import Checklist, ChecklistAnswer
from checklist.db.models.user import User
from checklist.db.models.company import Department

from ..report_data import get_attempt_data, format_attempt_result  # подробные данные для экспорта
from ..utils.timezone import to_moscow, format_moscow

logger = logging.getLogger(__name__)

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
                .filter(
                    ChecklistAnswer.user_id == user_id,
                    ChecklistAnswer.submitted_at.isnot(None),
                )
                .order_by(ChecklistAnswer.submitted_at.desc())
            )

            total = db.query(func.count(ChecklistAnswer.id)).filter(
                ChecklistAnswer.user_id == user_id,
                ChecklistAnswer.submitted_at.isnot(None),
            ).scalar() or 0

            rows = base.offset(offset).limit(limit).all()
            items = [
                {
                    "answer_id": r.answer_id,
                    "checklist_name": r.checklist_name,
                    "submitted_at": to_moscow(r.submitted_at) if r.submitted_at else None,
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

            result: str | None = None
            try:
                attempt_data = get_attempt_data(answer_id)
            except Exception as exc:
                logger.warning("[REPORT] get_attempt_data failed for answer_id=%s: %s", answer_id, exc)
                attempt_data = None

            if attempt_data and getattr(attempt_data, "is_scored", False):
                result = format_attempt_result(attempt_data)

            dt = to_moscow(ans.submitted_at)
            return {
                "checklist_name": checklist.name,
                "date": format_moscow(dt, "%d.%m.%Y"),
                "time": format_moscow(dt, "%H:%M"),
                "department": departments,
                "result": result,
            }

    def get_attempt(self, answer_id: int):
        """
        Полные данные попытки для экспорта (dataclass AttemptData) — используем готовую логику.
        """
        return get_attempt_data(answer_id)

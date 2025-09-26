# bot/repositories/questions.py
from __future__ import annotations
from typing import Any, Dict, List, Optional

from sqlalchemy import asc
from checklist.db.db import SessionLocal
from checklist.db.models.checklist import Checklist, ChecklistQuestion, ChecklistQuestionAnswer, ChecklistAnswer


class QuestionsRepo:
    """Доступ к вопросам чек-листа и связанной информации."""

    def get_for_checklist(self, checklist_id: int) -> List[Dict[str, Any]]:
        """Список вопросов (в порядке). Возвращаем простые dict'ы, безопасные для хэндлеров."""
        with SessionLocal() as db:
            q = (
                db.query(ChecklistQuestion)
                .filter(ChecklistQuestion.checklist_id == checklist_id)
            )

            # порядок: если есть поле order/position — используем, иначе по id
            if hasattr(ChecklistQuestion, "order"):
                q = q.order_by(asc(ChecklistQuestion.order))
            elif hasattr(ChecklistQuestion, "position"):
                q = q.order_by(asc(ChecklistQuestion.position))
            else:
                q = q.order_by(asc(ChecklistQuestion.id))

            items = []
            for row in q.all():
                items.append({
                    "id": row.id,
                    "text": getattr(row, "text", ""),
                    "type": getattr(row, "type", "text"),
                    "weight": getattr(row, "weight", 1),
                    "hint": getattr(row, "hint", None),
                    "options": getattr(row, "options", None),  # если в модели есть JSON-поле с вариантами
                })
            return items

    def get_question_ids(self, checklist_id: int) -> List[int]:
        with SessionLocal() as db:
            q = db.query(ChecklistQuestion.id).filter(ChecklistQuestion.checklist_id == checklist_id)
            if hasattr(ChecklistQuestion, "order"):
                q = q.order_by(asc(ChecklistQuestion.order))
            elif hasattr(ChecklistQuestion, "position"):
                q = q.order_by(asc(ChecklistQuestion.position))
            else:
                q = q.order_by(asc(ChecklistQuestion.id))
            return [row[0] for row in q.all()]

    def get_hint(self, question_id: int) -> Optional[str]:
        with SessionLocal() as db:
            row = db.query(ChecklistQuestion).get(question_id)  # type: ignore[arg-type]
            return getattr(row, "hint", None) if row else None

    def first_unanswered_for_attempt(self, answer_id: int) -> Optional[int]:
        """Находит первый НЕотвеченный вопрос для данной попытки, согласно порядку вопросов чек-листа."""
        with SessionLocal() as db:
            ans = db.query(ChecklistAnswer).get(answer_id)  # type: ignore[arg-type]
            if not ans:
                return None

            # id всех вопросов этого чек-листа
            qids_q = db.query(ChecklistQuestion.id).filter(ChecklistQuestion.checklist_id == ans.checklist_id)
            if hasattr(ChecklistQuestion, "order"):
                qids_q = qids_q.order_by(asc(ChecklistQuestion.order))
            elif hasattr(ChecklistQuestion, "position"):
                qids_q = qids_q.order_by(asc(ChecklistQuestion.position))
            else:
                qids_q = qids_q.order_by(asc(ChecklistQuestion.id))
            qids = [r[0] for r in qids_q.all()]

            # уже отвеченные
            answered = {
                r[0] for r in db.query(ChecklistQuestionAnswer.question_id)
                .filter(ChecklistQuestionAnswer.answer_id == answer_id).all()
            }

            for qid in qids:
                if qid not in answered:
                    return qid
            return None

# bot/repositories/questions.py
from __future__ import annotations
import json
from typing import Any, Dict, List, Optional

from sqlalchemy import asc
from sqlalchemy.orm import selectinload
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
                .options(selectinload(ChecklistQuestion.section))
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
                section_name = None
                section_id = getattr(row, "section_id", None)
                section_obj = getattr(row, "section", None)
                section_order = None
                if section_obj is not None:
                    section_name = getattr(section_obj, "name", None) or getattr(section_obj, "title", None)
                    section_order = getattr(section_obj, "order", None) or getattr(section_obj, "position", None)
                    if section_id is None:
                        section_id = getattr(section_obj, "id", None)
                if not section_name:
                    section_name = getattr(row, "section_name", None) or getattr(row, "section_title", None) or getattr(row, "group_name", None)

                meta = getattr(row, "meta", None)
                if meta and not section_name:
                    if isinstance(meta, str):
                        try:
                            meta = json.loads(meta)
                        except Exception:
                            meta = {}
                    if isinstance(meta, dict):
                        section_candidate = meta.get("section") or meta.get("section_name") or meta.get("group")
                        if isinstance(section_candidate, dict):
                            section_name = section_candidate.get("name") or section_candidate.get("title")
                        elif section_candidate:
                            section_name = str(section_candidate)
                items.append({
                    "id": row.id,
                    "text": getattr(row, "text", ""),
                    "type": getattr(row, "type", "text"),
                    "weight": getattr(row, "weight", 1),
                    "hint": getattr(row, "hint", None),
                    "options": getattr(row, "options", None),  # если в модели есть JSON-поле с вариантами
                    "require_photo": bool(getattr(row, "require_photo", False)),
                    "require_comment": bool(getattr(row, "require_comment", False)),
                    "section_id": section_id,
                    "section": section_name,
                    "section_order": section_order,
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

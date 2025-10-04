# bot/repositories/attempts.py
from __future__ import annotations
from typing import Dict, Optional
from datetime import datetime

from checklist.db.db import SessionLocal
from checklist.db.models.checklist import ChecklistAnswer, ChecklistQuestionAnswer


class AttemptsRepo:
    """Создание/поиск попытки, сохранение ответов, комментариев и фото."""

    def get_or_create_draft(self, user_id: int, checklist_id: int) -> int:
        """Возвращает id попытки. Если есть черновик (без submitted_at) — реюзаем, иначе создаём."""
        with SessionLocal() as db:
            draft = (
                db.query(ChecklistAnswer)
                .filter(
                    ChecklistAnswer.user_id == user_id,
                    ChecklistAnswer.checklist_id == checklist_id,
                    ChecklistAnswer.submitted_at.is_(None),
                )
                .first()
            )
            if draft:
                return draft.id

            new = ChecklistAnswer(
                user_id=user_id,
                checklist_id=checklist_id,
                started_at=datetime.utcnow(),
                submitted_at=None,
            )
            db.add(new)
            db.commit()
            db.refresh(new)
            return new.id

    def get_answers_for_attempt(self, answer_id: int) -> Dict[int, Dict[str, Optional[str]]]:
        with SessionLocal() as db:
            rows = (
                db.query(ChecklistQuestionAnswer)
                .filter(ChecklistQuestionAnswer.answer_id == answer_id)
                .all()
            )

            answers: Dict[int, Dict[str, Optional[str]]] = {}
            for row in rows:
                answers[row.question_id] = {
                    "answer": row.response_value,
                    "comment": row.comment,
                    "photo_path": row.photo_path,
                }
            return answers

    def save_answer(self, answer_id: int, question_id: int, value: Optional[str]) -> None:
        with SessionLocal() as db:
            row = (
                db.query(ChecklistQuestionAnswer)
                .filter(
                    ChecklistQuestionAnswer.answer_id == answer_id,
                    ChecklistQuestionAnswer.question_id == question_id,
                )
                .one_or_none()
            )
            if row:
                row.response_value = value
            else:
                row = ChecklistQuestionAnswer(
                    answer_id=answer_id,
                    question_id=question_id,
                    response_value=value,
                )
                db.add(row)
            db.commit()

    def save_comment(self, answer_id: int, question_id: int, comment: Optional[str]) -> None:
        with SessionLocal() as db:
            row = (
                db.query(ChecklistQuestionAnswer)
                .filter(
                    ChecklistQuestionAnswer.answer_id == answer_id,
                    ChecklistQuestionAnswer.question_id == question_id,
                )
                .one_or_none()
            )
            if row:
                row.comment = comment
            else:
                row = ChecklistQuestionAnswer(
                    answer_id=answer_id,
                    question_id=question_id,
                    comment=comment,
                )
                db.add(row)
            db.commit()

    def save_photo_path(self, answer_id: int, question_id: int, photo_path: Optional[str]) -> None:
        with SessionLocal() as db:
            row = (
                db.query(ChecklistQuestionAnswer)
                .filter(
                    ChecklistQuestionAnswer.answer_id == answer_id,
                    ChecklistQuestionAnswer.question_id == question_id,
                )
                .one_or_none()
            )
            if row:
                row.photo_path = photo_path
            else:
                row = ChecklistQuestionAnswer(
                    answer_id=answer_id,
                    question_id=question_id,
                    photo_path=photo_path,
                )
                db.add(row)
            db.commit()

    def finish_attempt(self, answer_id: int) -> None:
        """Помечаем попытку завершённой (заполняем submitted_at)."""
        with SessionLocal() as db:
            ans = db.query(ChecklistAnswer).get(answer_id)  # type: ignore[arg-type]
            if not ans:
                return
            if ans.submitted_at is None:
                ans.submitted_at = datetime.utcnow()
                db.commit()

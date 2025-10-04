# bot/repositories/attempts.py
from __future__ import annotations
from typing import Dict, Optional
from datetime import datetime

from sqlalchemy.orm import selectinload

from checklist.db.db import SessionLocal
from checklist.db.models.checklist import (
    ChecklistAnswer,
    ChecklistQuestionAnswer,
    ChecklistDraft,
    ChecklistDraftAnswer,
)


class AttemptsRepo:
    """Создание/поиск попытки, сохранение ответов, комментариев и фото."""

    def get_or_create_draft(self, user_id: int, checklist_id: int) -> int:
        """Возвращает id черновика. Если существует — обновляем updated_at и используем его."""
        with SessionLocal() as db:
            draft = (
                db.query(ChecklistDraft)
                .filter(
                    ChecklistDraft.user_id == user_id,
                    ChecklistDraft.checklist_id == checklist_id,
                )
                .first()
            )
            if draft:
                draft.updated_at = datetime.utcnow()
                db.commit()
                return draft.id

            new = ChecklistDraft(
                user_id=user_id,
                checklist_id=checklist_id,
                started_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(new)
            db.commit()
            db.refresh(new)
            return new.id

    def get_draft_id(self, user_id: int, checklist_id: int) -> Optional[int]:
        with SessionLocal() as db:
            draft = (
                db.query(ChecklistDraft.id)
                .filter(
                    ChecklistDraft.user_id == user_id,
                    ChecklistDraft.checklist_id == checklist_id,
                )
                .first()
            )
            return draft[0] if draft else None

    def get_draft_department(self, draft_id: int) -> Optional[str]:
        with SessionLocal() as db:
            draft = db.query(ChecklistDraft.department).filter(ChecklistDraft.id == draft_id).first()
            return draft[0] if draft else None

    def set_draft_department(self, draft_id: int, department: Optional[str]) -> None:
        with SessionLocal() as db:
            draft = db.query(ChecklistDraft).get(draft_id)  # type: ignore[arg-type]
            if not draft:
                return
            draft.department = department
            draft.updated_at = datetime.utcnow()
            db.commit()

    def get_answers_for_attempt(self, answer_id: int) -> Dict[int, Dict[str, Optional[str]]]:
        with SessionLocal() as db:
            rows = (
                db.query(ChecklistDraftAnswer)
                .filter(ChecklistDraftAnswer.draft_id == answer_id)
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
            draft = db.query(ChecklistDraft).get(answer_id)  # type: ignore[arg-type]
            if not draft:
                return

            row = (
                db.query(ChecklistDraftAnswer)
                .filter(
                    ChecklistDraftAnswer.draft_id == answer_id,
                    ChecklistDraftAnswer.question_id == question_id,
                )
                .one_or_none()
            )
            if row is None:
                row = ChecklistDraftAnswer(
                    draft_id=answer_id,
                    question_id=question_id,
                    response_value=value,
                )
                db.add(row)
            else:
                row.response_value = value
                row.updated_at = datetime.utcnow()

            draft.updated_at = datetime.utcnow()
            db.commit()

    def save_comment(self, answer_id: int, question_id: int, comment: Optional[str]) -> None:
        with SessionLocal() as db:
            draft = db.query(ChecklistDraft).get(answer_id)  # type: ignore[arg-type]
            if not draft:
                return

            row = (
                db.query(ChecklistDraftAnswer)
                .filter(
                    ChecklistDraftAnswer.draft_id == answer_id,
                    ChecklistDraftAnswer.question_id == question_id,
                )
                .one_or_none()
            )
            if row is None:
                row = ChecklistDraftAnswer(
                    draft_id=answer_id,
                    question_id=question_id,
                    comment=comment,
                )
                db.add(row)
            else:
                row.comment = comment
                row.updated_at = datetime.utcnow()

            draft.updated_at = datetime.utcnow()
            db.commit()

    def save_photo_path(self, answer_id: int, question_id: int, photo_path: Optional[str]) -> None:
        with SessionLocal() as db:
            draft = db.query(ChecklistDraft).get(answer_id)  # type: ignore[arg-type]
            if not draft:
                return

            row = (
                db.query(ChecklistDraftAnswer)
                .filter(
                    ChecklistDraftAnswer.draft_id == answer_id,
                    ChecklistDraftAnswer.question_id == question_id,
                )
                .one_or_none()
            )
            if row is None:
                row = ChecklistDraftAnswer(
                    draft_id=answer_id,
                    question_id=question_id,
                    photo_path=photo_path,
                )
                db.add(row)
            else:
                row.photo_path = photo_path
                row.updated_at = datetime.utcnow()

            draft.updated_at = datetime.utcnow()
            db.commit()

    def finish_attempt(self, draft_id: int) -> Optional[int]:
        """Переносит черновик в основную таблицу и возвращает id завершённой попытки."""
        with SessionLocal() as db:
            draft: ChecklistDraft | None = (
                db.query(ChecklistDraft)
                .options(selectinload(ChecklistDraft.answers))
                .get(draft_id)  # type: ignore[arg-type]
            )
            if not draft:
                return None

            final_answer = ChecklistAnswer(
                checklist_id=draft.checklist_id,
                user_id=draft.user_id,
                started_at=draft.started_at,
                submitted_at=datetime.utcnow(),
            )
            db.add(final_answer)
            db.flush()

            for answer in draft.answers:
                db.add(
                    ChecklistQuestionAnswer(
                        answer_id=final_answer.id,
                        question_id=answer.question_id,
                        response_value=answer.response_value,
                        comment=answer.comment,
                        photo_path=answer.photo_path,
                    )
                )

            db.delete(draft)
            db.commit()
            return final_answer.id

    def discard_attempt(self, draft_id: int) -> None:
        """Удаляет черновик попытки вместе с ответами."""
        with SessionLocal() as db:
            draft = db.query(ChecklistDraft).get(draft_id)  # type: ignore[arg-type]
            if not draft:
                return
            db.delete(draft)
            db.commit()

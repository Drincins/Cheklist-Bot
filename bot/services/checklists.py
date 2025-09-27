# bot/services/checklists.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..repositories.questions import QuestionsRepo
from ..repositories.attempts import AttemptsRepo


@dataclass
class ChecklistsService:
    """Бизнес-правила прохождения чек-листа: какой вопрос дальше, как сохранять ответ и т.п."""
    questions: QuestionsRepo = QuestionsRepo()
    attempts: AttemptsRepo = AttemptsRepo()

    # ---- чтение структуры ----
    def get_questions_for_checklist(self, checklist_id: int) -> List[Dict[str, Any]]:
        return self.questions.get_for_checklist(checklist_id)

    def get_first_unanswered(self, answer_id: int) -> Optional[int]:
        return self.questions.first_unanswered_for_attempt(answer_id)

    # ---- работа с попыткой ----
    def start_attempt(self, user_id: int, checklist_id: int) -> int:
        return self.attempts.get_or_create_draft(user_id=user_id, checklist_id=checklist_id)

    def get_attempt_answers(self, answer_id: int) -> Dict[int, Dict[str, Optional[str]]]:
        return self.attempts.get_answers_for_attempt(answer_id)

    def save_answer(self, answer_id: int, question_id: int, value: Optional[str]) -> None:
        self.attempts.save_answer(answer_id=answer_id, question_id=question_id, value=value)

    def save_comment(self, answer_id: int, question_id: int, comment: Optional[str]) -> None:
        self.attempts.save_comment(answer_id=answer_id, question_id=question_id, comment=comment)

    def save_photo(self, answer_id: int, question_id: int, photo_path: Optional[str]) -> None:
        self.attempts.save_photo_path(answer_id=answer_id, question_id=question_id, photo_path=photo_path)

    def finish(self, answer_id: int) -> None:
        self.attempts.finish_attempt(answer_id)

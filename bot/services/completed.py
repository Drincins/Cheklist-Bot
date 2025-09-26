# bot/services/completed.py
from __future__ import annotations
from dataclasses import dataclass

from ..repositories.answers import AnswersRepo

@dataclass
class CompletedService:
    answers: AnswersRepo = AnswersRepo()

    def get_paginated(self, user_id: int, offset: int, limit: int):
        return self.answers.get_completed_paginated(user_id=user_id, offset=offset, limit=limit)

    def get_report_preview(self, answer_id: int):
        return self.answers.get_report_preview(answer_id)

    def get_attempt(self, answer_id: int):
        return self.answers.get_attempt(answer_id)

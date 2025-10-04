# bot/repositories/checklists.py
from __future__ import annotations
from checklist.db.db import SessionLocal
from checklist.db.models.user import User
from checklist.db.models.role import Position
from checklist.db.models.checklist import Checklist

class ChecklistsRepo:
    def get_for_user(self, user_id: int):
        """
        Чек-листы, назначенные должности пользователя (Position.checklists).
        """
        with SessionLocal() as db:
            u: User | None = db.query(User).get(user_id)  # type: ignore[arg-type]
            if not u or not u.position_id:
                return []

            pos: Position | None = db.query(Position).get(u.position_id)  # type: ignore[arg-type]
            if not pos:
                return []

            # возвращаем простой список dict’ов для клавиатуры
            return [
                {"id": cl.id, "name": cl.name}
                for cl in (pos.checklists or [])
            ]

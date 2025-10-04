# bot/repositories/users.py
from __future__ import annotations
from typing import Any, Dict, Optional

import bcrypt
from sqlalchemy import func
from checklist.db.db import SessionLocal
from checklist.db.models.user import User
from checklist.db.models.company import Company

def _normalize_phone(phone: str | None) -> str:
    if not phone:
        return ""
    digits = "".join(ch for ch in phone if ch.isdigit())
    # берём последние 10 цифр, как в большинстве логик поиска
    return digits[-10:] if len(digits) >= 10 else digits

class UsersRepo:
    def find_by_name_phone_company(
        self,
        name: str,
        phone: str,
        company_id: int | None,
    ) -> Optional[Dict[str, Any]]:
        """
        Ищем пользователя по ФИО (LIKE, без регистра), телефону (нормализовано: последние 10 цифр)
        и компании (если передана). Возвращаем компактный dict для FSM.
        """
        name = (name or "").strip()
        norm_phone = _normalize_phone(phone)

        with SessionLocal() as db:
            q = db.query(User).filter(
                func.lower(User.name) == func.lower(name)
            )

            if norm_phone:
                # приведём phone пользователя так же к последним 10 цифрам
                q = q.filter(func.right(func.regexp_replace(User.phone, r'\D', '', 'g'), 10) == norm_phone) \
                    if db.bind.dialect.name == "postgresql" else q.filter(User.phone.like(f"%{norm_phone}"))

            if company_id is not None:
                q = q.filter(User.company_id == company_id)

            u: User | None = q.first()
            if not u:
                return None

            company: Company | None = db.query(Company).get(u.company_id)  # type: ignore[arg-type]
            dept_names = [d.name for d in (u.departments or [])]

            return {
                "id": u.id,
                "name": u.name,
                "phone": u.phone or "",
                "company_id": u.company_id,
                "company_name": company.name if company else "—",
                "position": getattr(getattr(u, "position", None), "name", "Не указано"),
                "department": ", ".join(dept_names) if dept_names else "Не указано",
                "departments": dept_names,
            }

    def find_by_credentials(self, login: str, password: str) -> Optional[Dict[str, Any]]:
        login = (login or "").strip()
        if not login or not password:
            return None

        with SessionLocal() as db:
            login_lower = login.lower()
            if not login_lower:
                return None
            q = db.query(User).filter(func.lower(User.login) == login_lower)
            user: User | None = q.first()
            if not user or not user.hashed_password:
                return None

            try:
                if not bcrypt.checkpw(password.encode(), user.hashed_password.encode()):
                    return None
            except ValueError:
                # некорректный hash
                return None

            company: Company | None = db.query(Company).get(user.company_id)  # type: ignore[arg-type]
            dept_names = [d.name for d in (user.departments or [])]

            return {
                "id": user.id,
                "name": user.name,
                "phone": user.phone or "",
                "company_id": user.company_id,
                "company_name": company.name if company else "—",
                "position": getattr(getattr(user, "position", None), "name", "Не указано"),
                "department": ", ".join(dept_names) if dept_names else "Не указано",
                "departments": dept_names,
            }

# bot/services/auth.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional

from ..repositories.users import UsersRepo
from ..repositories.checklists import ChecklistsRepo
from ..repositories.companies import CompaniesRepo

@dataclass
class AuthService:
    users: UsersRepo = UsersRepo()
    checklists: ChecklistsRepo = ChecklistsRepo()
    companies: CompaniesRepo = CompaniesRepo()

    def find_user(
        self,
        name: str,
        phone: str,
        company_id: int | None = None,
        company_name: str | None = None,
    ) -> Optional[Dict[str, Any]]:
        # если явно не передан id, но есть имя компании — найдём id
        if company_id is None and company_name:
            company_id = self.companies.get_id_by_name(company_name)
        return self.users.find_by_name_phone_company(
            name=name, phone=phone, company_id=company_id
        )

    def get_user_checklists(self, user_id: int):
        return self.checklists.get_for_user(user_id)

    def authenticate(self, login: str, password: str) -> Optional[Dict[str, Any]]:
        return self.users.find_by_credentials(login=login, password=password)

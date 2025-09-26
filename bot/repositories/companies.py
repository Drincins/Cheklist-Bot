# bot/repositories/companies.py
from __future__ import annotations
from typing import Optional
from sqlalchemy import func
from checklist.db.db import SessionLocal
from checklist.db.models.company import Company

class CompaniesRepo:
    def get_id_by_name(self, name: str | None) -> Optional[int]:
        if not name:
            return None
        with SessionLocal() as db:
            row = (
                db.query(Company)
                .filter(func.lower(Company.name) == func.lower(name.strip()))
                .first()
            )
            return row.id if row else None

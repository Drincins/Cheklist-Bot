import sys
import os
import re
from sqlalchemy import func
from sqlalchemy.orm import joinedload
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from checklist.db import SessionLocal
from checklist.models import Company, User, Checklist, ChecklistQuestion, ChecklistAnswer
from datetime import datetime
from checklist.models import ChecklistQuestionAnswer

    
def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    return digits[-10:] if len(digits) >= 10 else digits

def find_user_by_name_phone_company(name: str, phone: str, company_name: str | None):
    clean_phone = normalize_phone(phone)

    with SessionLocal() as db:
        query = db.query(User, Company.name.label("company_name")).join(Company, User.company_id == Company.id).options(
            joinedload(User.position)
        ).filter(
            User.name == name.strip(),
            func.right(User.phone, 10) == clean_phone,
            User.role == "employee"
        )

        if company_name:
            query = query.filter(Company.name == company_name.strip())

        result = query.first()

        if result:
            user, company_name = result
            return {
                "id": user.id,
                "name": user.name,
                "phone": user.phone,
                "company_id": user.company_id,
                "company_name": company_name,
                "position": user.position.name if user.position else "Не указано",
            }
        return None


def get_checklists_for_user(user_id: int, page: int = 0, page_size: int = 8) -> list[dict]:
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if not user or not user.position:
            return []
        checklists = user.position.checklists[page * page_size: (page + 1) * page_size]
        return [{"id": c.id, "name": c.name} for c in checklists]

def count_checklists_for_user(user_id: int) -> int:
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if not user or not user.position:
            return 0
        return len(user.position.checklists)

def get_questions_for_checklist(checklist_id: int) -> list[dict]:
    with SessionLocal() as db:
        questions = (
            db.query(ChecklistQuestion)
            .filter_by(checklist_id=checklist_id)
            .order_by(ChecklistQuestion.order)
            .all()
        )
        return [{
            "id": q.id,
            "text": q.text,
            "type": q.type,
            "order": q.order,
            "meta": q.meta
        } for q in questions]

def get_checklist_by_id(checklist_id: int) -> dict | None:
    with SessionLocal() as db:
        checklist = db.get(Checklist, checklist_id)
        if checklist:
            return {
                "id": checklist.id,
                "name": checklist.name,
                "is_scored": checklist.is_scored  # <-- используем это
            }
        return None


def get_completed_checklists(user_id: int, page: int = 0, page_size: int = 8) -> list[dict]:
    with SessionLocal() as db:
        results = (
            db.query(ChecklistAnswer.checklist_id, Checklist.name, ChecklistAnswer.timestamp)
            .join(Checklist, Checklist.id == ChecklistAnswer.checklist_id)
            .filter(ChecklistAnswer.user_id == user_id)
            .order_by(ChecklistAnswer.submitted_at.desc())
            .distinct(ChecklistAnswer.checklist_id)
            .offset(page * page_size)
            .limit(page_size)
            .all()
        )
        return [{"id": r.checklist_id, "name": r.name, "timestamp": r.timestamp} for r in results]

def get_answers_for_checklist(user_id: int, checklist_id: int) -> list[dict]:
    with SessionLocal() as db:
        results = (
            db.query(ChecklistQuestion.text, ChecklistQuestionAnswer.response_value)
            .join(ChecklistQuestionAnswer, ChecklistQuestion.id == ChecklistQuestionAnswer.question_id)
            .join(ChecklistAnswer, ChecklistAnswer.id == ChecklistQuestionAnswer.answer_id)
            .filter(
                ChecklistAnswer.user_id == user_id,
                ChecklistAnswer.checklist_id == checklist_id
            )
            .order_by(ChecklistQuestion.order)
            .all()
        )
        return [{"question": r[0], "answer": r[1]} for r in results]



def save_checklist_with_answers(user_id: int, checklist_id: int, answers: list[dict]):
    with SessionLocal() as db:
        session = ChecklistAnswer(
            user_id=user_id,
            checklist_id=checklist_id,
            submitted_at=datetime.utcnow()
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        for ans in answers:
            db.add(ChecklistQuestionAnswer(
                answer_id=session.id,
                question_id=ans["question_id"],
                response_value=ans.get("response_value"),
                comment=ans.get("comment"),
                photo_path=ans.get("photo_path"),
                created_at=datetime.utcnow()
            ))
        db.commit()
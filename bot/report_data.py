# bot/report_data.py
import datetime as dt
import json
import re
import os
from dataclasses import dataclass
from typing import Optional, List, Any, Dict

from checklist.db.db import SessionLocal
from checklist.db.models.checklist import (
    Checklist, ChecklistAnswer, ChecklistQuestion, ChecklistQuestionAnswer
)
from checklist.db.models.user import User
from checklist.db.models.company import Company


@dataclass
class AnswerRow:
    number: int
    question: str
    qtype: str
    answer: str
    comment: Optional[str] = None
    score: Optional[float] = None    # набранный балл
    weight: Optional[float] = None   # максимальный вес вопроса
    photo_path: Optional[str] = None


@dataclass
class AttemptData:
    attempt_id: int
    checklist_name: str
    user_name: str
    company_name: Optional[str]
    submitted_at: dt.datetime
    answers: List[AnswerRow]


# ---------------- helpers ----------------

def _dbg_enabled() -> bool:
    return os.getenv("DEBUG_SCORES", "").strip().lower() in {"1", "true", "yes", "on"}


def _log(msg: str):
    if _dbg_enabled():
        print(msg)


def _as_dict(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except Exception:
            return {}
    return {}


def _first_present(d: dict, keys: List[str]):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def _to_float(v) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def _merge_meta(*parts: dict) -> dict:
    merged: Dict[str, Any] = {}
    for p in parts:
        if isinstance(p, dict):
            merged.update(p)
    return merged


def _extract_weight(meta: dict) -> Optional[float]:
    candidate = _first_present(meta, [
        # англ варианты
        "weight", "score_weight", "points", "max_points", "max_score", "score", "weight_value",
        # русские
        "вес", "балл", "баллы",
    ])
    return _to_float(candidate)


def _extract_scale_max(meta: dict) -> Optional[float]:
    # прямые ключи
    direct = _first_present(meta, ["max", "scale_max", "max_value", "upper", "upper_bound"])
    mx = _to_float(direct)
    if mx:
        return mx

    # options: len / max(value)
    opts = meta.get("options")
    if isinstance(opts, (list, tuple)) and len(opts) > 0:
        if not isinstance(opts[0], dict):
            return _to_float(len(opts)) or None
        vals = []
        for it in opts:
            if isinstance(it, dict):
                cand = _first_present(it, ["value", "val", "score", "points"])
                f = _to_float(cand)
                if f is not None:
                    vals.append(f)
        if vals:
            return max(vals)
        return _to_float(len(opts)) or None

    # values / choices
    for key in ["values", "choices"]:
        seq = meta.get(key)
        if isinstance(seq, (list, tuple)) and len(seq) > 0:
            return _to_float(len(seq)) or None

    # range "1-5"
    rng = meta.get("range")
    if isinstance(rng, str):
        m = re.match(r"\s*(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)\s*$", rng)
        if m:
            return _to_float(m.group(2))

    return None


# ---------------- main ----------------

def get_attempt_data(attempt_id: int) -> AttemptData:
    """
    Считает score/weight так:
      - yes/no:   Да → score=weight, иначе 0
      - scale:    score = weight * (value / scale_max), scale_max берём из meta/столбцов; дефолт 10
      - прочие:   score=None
    Источники данных для weight/scale_max (по убыв. приоритета):
      1) ChecklistQuestion.meta
      2) Отдельные числовые поля у ChecklistQuestion (если есть): weight/score_weight/max/scale_max/max_value
    """
    with SessionLocal() as db:
        attempt: ChecklistAnswer = (
            db.query(ChecklistAnswer)
            .filter(ChecklistAnswer.id == attempt_id)
            .one()
        )

        checklist_name = (
            db.query(Checklist.name)
            .filter(Checklist.id == attempt.checklist_id)
            .scalar()
            or f"Checklist #{attempt.checklist_id}"
        )

        user_row = (
            db.query(User.name, User.company_id)
            .filter(User.id == attempt.user_id)
            .first()
        )
        user_name = user_row.name if user_row else "Неизвестный сотрудник"

        company_name = None
        if user_row and user_row.company_id:
            company_name = (
                db.query(Company.name)
                .filter(Company.id == user_row.company_id)
                .scalar()
            )

        submitted_at = attempt.submitted_at or dt.datetime.utcnow()

        # вопросы (meta берём сразу), чтобы сохранить порядок
        q_sub = (
            db.query(
                ChecklistQuestion.id,
                ChecklistQuestion.text,
                ChecklistQuestion.type,
                ChecklistQuestion.order,
                ChecklistQuestion.meta,
            )
            .filter(ChecklistQuestion.checklist_id == attempt.checklist_id)
            .subquery()
        )

        # ответы этой попытки (без meta у ответа)
        q_and_a = (
            db.query(
                q_sub.c.id.label("qid"),
                q_sub.c.text.label("qtext"),
                q_sub.c.type.label("qtype"),
                q_sub.c.order.label("qorder"),
                q_sub.c.meta.label("qmeta"),
                ChecklistQuestionAnswer.response_value,
                ChecklistQuestionAnswer.comment,
                ChecklistQuestionAnswer.photo_path,
            )
            .outerjoin(
                ChecklistQuestionAnswer,
                (ChecklistQuestionAnswer.question_id == q_sub.c.id)
                & (ChecklistQuestionAnswer.answer_id == attempt_id)
            )
            .order_by(q_sub.c.order.asc())
            .all()
        )

        # кэш: question_id -> ChecklistQuestion (для отдельных колонок)
        q_cache: Dict[int, ChecklistQuestion] = {}

        def _load_question(qid: int) -> Optional[ChecklistQuestion]:
            if qid in q_cache:
                return q_cache[qid]
            obj = db.get(ChecklistQuestion, qid)
            q_cache[qid] = obj
            return obj

        rows: List[AnswerRow] = []
        for idx, row in enumerate(q_and_a, start=1):
            answer_raw = row.response_value
            answer_str = "" if answer_raw is None else str(answer_raw)

            # meta из вопроса
            m_q = _as_dict(row.qmeta)

            # если у модели есть отдельные числовые поля — добавим в meta
            qobj = _load_question(row.qid)
            m_cols: Dict[str, Any] = {}
            if qobj is not None:
                for attr in ("weight", "score_weight", "points", "max_points", "max_score",
                             "max", "scale_max", "max_value"):
                    if hasattr(qobj, attr):
                        try:
                            val = getattr(qobj, attr)
                        except Exception:
                            val = None
                        if val is not None:
                            m_cols[attr] = val

            meta_all = _merge_meta(m_q, m_cols)

            weight    = _extract_weight(meta_all)
            scale_max = _extract_scale_max(meta_all)

            qtype = (row.qtype or "").lower().strip()
            score: Optional[float] = None

            if weight is not None:
                if qtype in {"yesno", "boolean", "bool", "yn"}:
                    s = answer_str.strip().lower()
                    score = weight if s in {"yes", "да", "true", "1"} else 0.0
                elif qtype in {"scale", "rating"}:
                    try:
                        val = float(answer_str) if answer_str.strip() != "" else 0.0
                    except Exception:
                        val = 0.0
                    mx = scale_max if (scale_max and scale_max > 0) else 10.0
                    score = weight * (val / mx)
                else:
                    score = None

            if weight is None:
                _log(f"[SCORE] No weight for Q{idx} (id={row.qid}): '{row.qtext[:50]}', meta_all={meta_all}")
            else:
                _log(f"[SCORE] Q{idx} (id={row.qid}): weight={weight}, type={qtype}, ans='{answer_str}', scale_max={scale_max} -> score={score}")

            rows.append(AnswerRow(
                number=idx,
                question=row.qtext,
                qtype=row.qtype,
                answer=answer_str,
                comment=row.comment,
                score=score,
                weight=weight,
                photo_path=row.photo_path
            ))

        return AttemptData(
            attempt_id=attempt_id,
            checklist_name=checklist_name,
            user_name=user_name,
            company_name=company_name,
            submitted_at=submitted_at,
            answers=rows
        )

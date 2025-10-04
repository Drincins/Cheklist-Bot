# bot/utils/checklist_mode.py
from collections import OrderedDict
from typing import List

def chunk_text(s: str, limit: int = 3500) -> List[str]:
    """Разбивает длинный текст на части, чтобы Telegram не ругался на лимит 4096 символов."""
    parts = []
    while s:
        if len(s) <= limit:
            parts.append(s)
            break
        cut = s.rfind("\n\n", 0, limit)
        if cut == -1:
            cut = s.rfind("\n", 0, limit)
        if cut == -1:
            cut = limit
        parts.append(s[:cut])
        s = s[cut:].lstrip()
    return parts

def group_questions_by_section(questions: list[dict]) -> List[dict]:
    """Собирает вопросы по разделам, сохраняя порядок первого появления."""
    sections: OrderedDict[tuple[int | None, str], dict] = OrderedDict()

    for q in questions:
        raw_name = q.get("section") or q.get("section_name") or q.get("group_name")
        title = str(raw_name).strip() if raw_name else ""
        if not title:
            title = "Без раздела"
        section_id = q.get("section_id")
        key = (section_id, title)
        bucket = sections.setdefault(key, {"title": title, "items": []})
        bucket["items"].append(q)

    return list(sections.values())


def render_full_checklist(questions: list[dict]) -> str:
    """Собираем весь список вопросов в один текст (без обращения к БД или состоянию)."""
    lines = ["📜 *Полный список вопросов*"]

    for section in group_questions_by_section(questions):
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(f"*{section['title']}*")
        for idx, q in enumerate(section["items"], start=1):
            title = (q.get("text") or q.get("question_text") or "").strip() or f"Вопрос #{idx}"
            lines.append(f"{idx}. {title}")

    return "\n".join(lines)

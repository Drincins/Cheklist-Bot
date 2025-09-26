# bot/utils/checklist_mode.py
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

def render_full_checklist(questions: list[dict]) -> str:
    """Собираем весь список вопросов в один текст (без обращения к БД или состоянию)."""
    lines = ["📜 *Полный список вопросов*\n"]
    for i, q in enumerate(questions, start=1):
        qtype = q.get("type") or q.get("question_type") or "text"
        if qtype in ("yes_no", "yesno"):
            kind = "Да/Нет"
        elif qtype == "scale":
            kind = "Шкала 1–5"
        else:
            kind = "Текст"
        title = (q.get("text") or q.get("question_text") or "").strip() or f"Вопрос #{i}"
        lines.append(f"*{i}.* {title}\n_Тип:_ {kind}\n")
    return "\n".join(lines)

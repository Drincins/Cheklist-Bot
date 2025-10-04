# bot/utils/checklist_text.py

def render_question_text(question: dict, draft: dict) -> str:
    """
    Текст вопроса + индикаторы: выбранный ответ, есть ли комментарий/фото.
    """
    extra = []
    if draft.get("answer") is not None:
        extra.append(f"🟩 Ответ: *{draft['answer']}*")
    if draft.get("comment"):
        extra.append("💬 Комментарий добавлен")
    if draft.get("photo_path"):
        extra.append("📷 Фото добавлено")

    suffix = ("\n\n" + "\n".join(extra)) if extra else ""
    return f"{question['text']}{suffix}"


def render_answers_summary(questions: list[dict], answers_map: dict) -> str:
    """
    Короткое резюме ответов + примитивные метрики (процент «да», средняя шкала).
    """
    lines = ["🗂 *Ваши ответы:*\n"]
    yes_total = yes_cnt = 0
    scale_vals: list[float] = []

    for q in questions:
        d = answers_map.get(q["id"], {})
        a = d.get("answer")
        lines.append(f"— {q['text']}: *{a if a is not None else '—'}*")

        if q["type"] == "yesno":
            yes_total += 1
            if str(a).lower() == "yes":
                yes_cnt += 1
        elif q["type"] == "scale" and a is not None:
            try:
                scale_vals.append(float(a))
            except Exception:
                pass

    parts = []
    if yes_total:
        parts.append(f"{round(100 * yes_cnt / yes_total)}% «да»")
    if scale_vals:
        parts.append(f"{round(100 * (sum(scale_vals)/len(scale_vals)) / 5)}% шкала")
    if parts:
        lines.append("\n📊 Итог: " + " / ".join(parts))

    return "\n".join(lines)

import streamlit as st
import os
import pandas as pd
from checklist.db.db import SessionLocal
from checklist.db.models import (
    User,
    Checklist,
    ChecklistAnswer,
    ChecklistQuestion,
    ChecklistQuestionAnswer,
)
from sqlalchemy.exc import IntegrityError

# --- Локальное хранилище фото ---
os.makedirs("media", exist_ok=True)


# --- Загрузка фото через Telegram Bot (по file_id) ---
def download_photos_via_bot(token: str):
    """
    Скачивает все фотографии по file_id из ChecklistQuestionAnswer.photo_path,
    если там хранится file_id (а не локальный путь). Уже скачанные не трогаем.
    """
    import asyncio
    from aiogram import Bot

    bot = Bot(token=token)

    async def _inner():
        db = SessionLocal()
        answers = db.query(ChecklistQuestionAnswer).all()
        count, errors = 0, 0
        for ans in answers:
            file_id = ans.photo_path
            # Считаем, что если НЕ .jpg/.png, то это file_id
            if file_id and not str(file_id).lower().endswith((".jpg", ".jpeg", ".png")):
                dest_path = f"media/photo_{ans.id}.jpg"
                if os.path.exists(dest_path):
                    continue
                try:
                    file = await bot.get_file(file_id)
                    await bot.download_file(file.file_path, destination=dest_path)
                    ans.photo_path = dest_path
                    db.commit()
                    count += 1
                except Exception as e:
                    errors += 1
                    print(f"Ошибка скачивания {file_id}: {e}")
        db.close()
        return count, errors

    return asyncio.run(_inner())


# =======================
#      ОЦЕНОЧНЫЕ УТИЛИТЫ
# =======================
def _get_weight(question: ChecklistQuestion) -> int:
    """
    Вес вопроса: берем поле .weight, затем из question.meta['weight'], иначе 1.
    Любые ошибки — дефолт 1.
    """
    try:
        if getattr(question, "weight", None) is not None:
            return int(question.weight)
        meta = getattr(question, "meta", None)
        if isinstance(meta, dict) and "weight" in meta:
            return int(meta.get("weight") or 1)
    except Exception:
        pass
    return 1


def _is_yes(value: str) -> bool:
    """
    Унификация «да/нет» ответов.
    """
    if value is None:
        return False
    s = str(value).strip().lower()
    return s in {"да", "yes", "y", "true", "1", "ok", "✔", "✅", "пройдено", "выполнено"}


def _parse_scale(value: str) -> int:
    """
    Парсим шкалу 0..10 (строка/число). Если не удалось — 0.
    """
    try:
        v = int(float(str(value).replace(",", ".").strip()))
        return max(0, min(10, v))
    except Exception:
        return 0


def compute_answer_score(db, ans: ChecklistAnswer):
    """
    Считаем оценку прохождения ответа ans.
    Учитываем вопросы типов 'yesno' и 'scale':
      - yesno: да=1, нет=0
      - scale: 0..10 => 0.0..1.0
    Итог: сумма(v * weight) и максимум: сумма(weight).
    Возвращаем (score, max_score, percent) или (None, None, None), если нечего считать.
    """
    # Вопросы по данному чек-листу
    questions = {
        q.id: q
        for q in db.query(ChecklistQuestion).filter_by(checklist_id=ans.checklist_id).all()
    }
    if not questions:
        return (None, None, None)

    q_answers = db.query(ChecklistQuestionAnswer).filter_by(answer_id=ans.id).all()
    if not q_answers:
        return (None, None, None)

    total_w = 0
    got = 0.0

    for qa in q_answers:
        q = questions.get(qa.question_id)
        if not q:
            continue
        # Учитываем только yesno/scale
        if q.type not in ("yesno", "scale"):
            continue

        w = _get_weight(q)
        total_w += w

        if q.type == "yesno":
            v = 1.0 if _is_yes(qa.response_value) else 0.0
        else:  # scale
            v = _parse_scale(qa.response_value) / 10.0

        got += v * w

    if total_w == 0:
        return (None, None, None)

    percent = round(got / total_w * 100, 1)
    return (round(got, 2), total_w, percent)


# =======================
#        UI ВКЛАДКИ
# =======================
def reports_tab(company_id=None):
    st.title("📊 Отчёты по чек‑листам")

    # -------- Кнопка обновления изображений --------
    TOKEN = "7346157568:AAF_VYFkjq2tnyGrLykmb44ILNVdUbdGhbI"
    if st.button("🔁 Обновить изображения (скачать все фото из Telegram)"):
        with st.spinner("Загрузка фото..."):
            count, errors = download_photos_via_bot(TOKEN)
            st.success(f"Скачано файлов: {count}. Ошибок: {errors}")
        st.rerun()

    db = SessionLocal()

    # --- Фильтр по чек-листу (селект) ---
    # Собираем список чек-листов, чтобы показать названия
    checklists = db.query(Checklist).all()
    cl_map = {cl.id: cl.name for cl in checklists}
    cl_options = ["Все чек-листы"] + [cl_map[cid] for cid in sorted(cl_map, key=lambda x: cl_map[x].lower())]
    selected_cl_name = st.selectbox("Фильтр: чек-лист", cl_options)

    base_q = db.query(ChecklistAnswer).order_by(ChecklistAnswer.submitted_at.desc())
    if selected_cl_name != "Все чек-листы":
        selected_cl_id = next((cid for cid, name in cl_map.items() if name == selected_cl_name), None)
        answers = base_q.filter(ChecklistAnswer.checklist_id == selected_cl_id).all()
    else:
        answers = base_q.all()

    if not answers:
        st.info("Нет ответов по чек‑листам под выбранный фильтр.")
        db.close()
        return

    # --- Сводная таблица по ответам (с оценкой) ---
    rows = []
    for ans in answers:
        user = db.query(User).get(ans.user_id)
        checklist = db.query(Checklist).get(ans.checklist_id)
        score, max_score, percent = compute_answer_score(db, ans)

        rows.append(
            {
                "ID ответа": ans.id,
                "Сотрудник": user.name if user else f"user_id={ans.user_id}",
                "Чек-лист": checklist.name if checklist else f"checklist_id={ans.checklist_id}",
                "Дата": ans.submitted_at.strftime("%Y-%m-%d %H:%M") if ans.submitted_at else "–",
                "Оценка (%)": f"{percent}%" if percent is not None else "—",
            }
        )

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True)

    # --- Детализация выбранного ответа ---
    ids = df["ID ответа"].tolist()
    if ids:
        selected_id = st.selectbox("Посмотреть детали ответа (ID):", ids)
        if selected_id:
            ans = db.query(ChecklistAnswer).get(int(selected_id))
            user = db.query(User).get(ans.user_id)
            checklist = db.query(Checklist).get(ans.checklist_id)

            st.markdown(
                f"### {user.name if user else f'user_id={ans.user_id}'} — "
                f"{checklist.name if checklist else f'checklist_id={ans.checklist_id}'} "
                f"({ans.submitted_at.strftime('%Y-%m-%d %H:%M') if ans.submitted_at else '–'})"
            )

            q_answers = (
                db.query(ChecklistQuestionAnswer)
                .filter_by(answer_id=ans.id)
                .all()
            )

            for q_ans in q_answers:
                question = db.query(ChecklistQuestion).get(q_ans.question_id)
                q_title = question.text if question else f"question_id={q_ans.question_id}"
                st.markdown(
                    f"**{q_title}**\n\n"
                    f"Ответ: {q_ans.response_value if (q_ans.response_value not in (None, '')) else '—'}  "
                    + (f"\nКомментарий: {q_ans.comment}" if q_ans.comment else "")
                )

                # Фото/файл
                if q_ans.photo_path:
                    p = str(q_ans.photo_path)
                    if p.lower().endswith((".png", ".jpg", ".jpeg")) and os.path.exists(p):
                        st.image(p, caption="Фото")
                    else:
                        st.caption(f"Файл: `{p}`")

                st.markdown("---")

            # --- Итоговая оценка внизу деталей ---
            score, max_score, percent = compute_answer_score(db, ans)
            if percent is not None:
                st.info(f"**Итоговая оценка:** {score} из {max_score}  ·  **{percent}%**")
            else:
                st.caption("Для этого ответа нет оцениваемых вопросов (yesno/scale).")

    db.close()

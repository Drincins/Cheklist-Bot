import streamlit as st
import os
from checklist.db import SessionLocal
from checklist.models import User, Checklist, ChecklistAnswer, ChecklistQuestion, ChecklistQuestionAnswer
from sqlalchemy.exc import IntegrityError

# --- Импорт aiogram только если нажата кнопка ---
os.makedirs("media", exist_ok=True)
def download_photos_via_bot(token):
    import asyncio
    from aiogram import Bot

    bot = Bot(token=token)
    async def _inner():
        db = SessionLocal()
        answers = db.query(ChecklistQuestionAnswer).all()
        count, errors = 0, 0
        for ans in answers:
            file_id = ans.photo_path
            if file_id and not file_id.endswith(('.jpg', '.jpeg', '.png')):
                dest_path = f"media/photo_{ans.id}.jpg"
                # Не скачивать, если файл уже есть
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

def reports_tab(company_id=None):
    st.title("📊 Все ответы по чек‑листам (без фильтров)")

    # -------- Кнопка обновления изображений --------
    TOKEN = "7346157568:AAF_VYFkjq2tnyGrLykmb44ILNVdUbdGhbI"
    if st.button("🔁 Обновить изображения (скачать все фото из Telegram)"):
        with st.spinner("Загрузка фото..."):
            count, errors = download_photos_via_bot(TOKEN)
            st.success(f"Скачано файлов: {count}. Ошибок: {errors}")
        st.rerun()

    db = SessionLocal()
    answers = db.query(ChecklistAnswer).order_by(ChecklistAnswer.submitted_at.desc()).all()

    if not answers:
        st.info("Нет ни одного ответа по чек‑листам в базе.")
        db.close()
        return

    data = []
    for ans in answers:
        user = db.query(User).get(ans.user_id)
        checklist = db.query(Checklist).get(ans.checklist_id)
        row = {
            "Сотрудник": user.name if user else f"user_id={ans.user_id}",
            "Чек-лист": checklist.name if checklist else f"checklist_id={ans.checklist_id}",
            "Дата": ans.submitted_at.strftime('%Y-%m-%d %H:%M') if ans.submitted_at else "–",
            "ID ответа": ans.id,
        }
        data.append(row)
    st.dataframe(data, use_container_width=True)

    # --- Детализация по выбранному ответу
    ids = [row["ID ответа"] for row in data]
    if ids:
        selected_id = st.selectbox("Посмотреть детали ответа (ID):", ids)
        if selected_id:
            ans = db.query(ChecklistAnswer).get(selected_id)
            user = db.query(User).get(ans.user_id)
            checklist = db.query(Checklist).get(ans.checklist_id)
            st.markdown(f"### {user.name if user else f'user_id={ans.user_id}'} — {checklist.name if checklist else f'checklist_id={ans.checklist_id}'} ({ans.submitted_at.strftime('%Y-%m-%d %H:%M') if ans.submitted_at else '–'})")
            q_answers = db.query(ChecklistQuestionAnswer).filter_by(answer_id=ans.id).all()
            for q_ans in q_answers:
                question = db.query(ChecklistQuestion).get(q_ans.question_id)
                st.markdown(
                    f"**{question.text if question else f'question_id={q_ans.question_id}'}**\n\n"
                    f"Ответ: {q_ans.response_value}  "
                    + (f"\nКомментарий: {q_ans.comment}" if q_ans.comment else "")
                )
                # ----- ФОТО
                if q_ans.photo_path:
                    if q_ans.photo_path.endswith(('.png', '.jpg', '.jpeg')) and os.path.exists(q_ans.photo_path):
                        st.image(q_ans.photo_path, caption="Фото")
                    else:
                        st.markdown(f"**[file_id или ссылка на фото не найдена]**: `{q_ans.photo_path}`")
                st.markdown("---")

    db.close()

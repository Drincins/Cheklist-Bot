import streamlit as st
import os
from datetime import datetime
import pandas as pd
from typing import Optional, Tuple, Dict
from checklist.db.db import SessionLocal
from bot.config import BOT_TOKEN
from checklist.db.models import (
    User,
    Checklist,
    ChecklistAnswer,
    ChecklistQuestion,
    ChecklistQuestionAnswer,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

# =======================
#     КОНСТАНТЫ/НАСТРОЙКИ
# =======================

# Базовая шкала для оцениваемых вопросов
SCALE_MIN = 1
SCALE_MAX = 5  # 1 = 0, 5 = 1 (нормированное значение)

YES_TOKENS = {"да", "yes", "y", "true", "1", "ok", "✔", "✅", "пройдено", "выполнено"}

MEDIA_DIR = "media"
FALLBACK_EXT = ".jpg"
os.makedirs(MEDIA_DIR, exist_ok=True)

# =======================
#      ФОТО: УТИЛИТЫ
# =======================

def _is_local_image_path(s: Optional[str]) -> bool:
    if not s:
        return False
    s = str(s).strip().lower()
    return s.endswith((".jpg", ".jpeg", ".png"))

def _local_photo_path_for(qa_id: int) -> str:
    return os.path.join(MEDIA_DIR, f"qa_{qa_id}{FALLBACK_EXT}")

def ensure_local_photo(qa: ChecklistQuestionAnswer, db_session, bot_token: Optional[str] = None) -> Optional[str]:
    """
    Возвращает локальный путь к изображению для ответа qa.
      1) Если в БД уже локальный путь и файл существует — вернуть его.
      2) Если локального нет, но в папке есть media/qa_<id>.jpg — проставить в БД и вернуть.
      3) Если в БД лежит file_id и указан bot_token — скачать, сохранить в media/qa_<id>.jpg, обновить БД.
      4) Иначе вернуть None.
    """
    cur = (qa.photo_path or "").strip()
    # 1) Уже локальный и есть на диске
    if _is_local_image_path(cur) and os.path.exists(cur):
        return cur

    # 2) Детерминированный путь по id
    candidate = _local_photo_path_for(qa.id)
    if os.path.exists(candidate):
        if cur != candidate:
            qa.photo_path = candidate
            try:
                db_session.commit()
            except Exception:
                db_session.rollback()
        return candidate

    # 3) Похоже на file_id → качаем из ТГ
    if not _is_local_image_path(cur) and cur and bot_token:
        try:
            import asyncio
            from aiogram import Bot

            async def _dl():
                bot = Bot(token=bot_token)
                file = await bot.get_file(cur)
                await bot.download_file(file.file_path, destination=candidate)

            asyncio.run(_dl())
            if os.path.exists(candidate):
                qa.photo_path = candidate
                try:
                    db_session.commit()
                except Exception:
                    db_session.rollback()
                return candidate
        except Exception as e:
            print(f"[ensure_local_photo] download error for {cur}: {e}")

    return None

def download_photos_via_bot(token: str) -> Tuple[int, int]:
    """
    Проходит по всем ответам и гарантирует локальную копию (если в БД file_id).
    Возвращает (скачано, ошибок).
    """
    import asyncio
    from aiogram import Bot

    async def _inner():
        db = SessionLocal()   # именно скобки!
        df = _answers_df_for_all(db)
        try:
            bot = Bot(token=token)
            answers = db.query(ChecklistQuestionAnswer).all()
            count, errors = 0, 0
            for qa in answers:
                cur = (qa.photo_path or "").strip()
                # уже локальный и лежит — пропускаем
                if _is_local_image_path(cur) and os.path.exists(cur):
                    continue
                # детерминированный путь на диске
                candidate = _local_photo_path_for(qa.id)
                if os.path.exists(candidate):
                    if cur != candidate:
                        qa.photo_path = candidate
                        db.commit()
                    continue
                # если похоже на file_id — качаем
                if not _is_local_image_path(cur) and cur:
                    try:
                        file = await bot.get_file(cur)
                        await bot.download_file(file.file_path, destination=candidate)
                        if os.path.exists(candidate):
                            qa.photo_path = candidate
                            db.commit()
                            count += 1
                    except Exception as e:
                        errors += 1
                        print(f"[download_photos_via_bot] {cur} -> error: {e}")
            return count, errors
        finally:
            db.close()

    return asyncio.run(_inner())

def sync_local_photos_from_folder() -> int:
    """
    Проставляет в БД локальный путь media/qa_<id>.jpg, если файл есть в папке,
    а в БД путь пустой/не локальный/указан несуществующий файл.
    """
    db = SessionLocal()   # именно скобки!
    df = _answers_df_for_all(db)

    try:
        updated = 0
        files = [
            f for f in os.listdir(MEDIA_DIR)
            if f.startswith("qa_") and f.lower().endswith((".jpg", ".jpeg", ".png"))
        ]
        if not files:
            return 0
        by_id: Dict[int, str] = {}
        for f in files:
            name, ext = os.path.splitext(f)
            parts = name.split("_")
            if len(parts) == 2 and parts[1].isdigit():
                aid = int(parts[1])
                by_id[aid] = os.path.join(MEDIA_DIR, f)
        if not by_id:
            return 0

        qas = db.query(ChecklistQuestionAnswer)\
                .filter(ChecklistQuestionAnswer.id.in_(list(by_id.keys())))\
                .all()

        for qa in qas:
            desired = by_id.get(qa.id)
            if not desired:
                continue
            cur = (qa.photo_path or "").strip()
            if (not _is_local_image_path(cur)) or (cur != desired) or (cur and not os.path.exists(cur)):
                qa.photo_path = desired
                updated += 1
        if updated:
            db.commit()
        return updated
    finally:
        db.close()

# =======================
#      ОЦЕНОЧНЫЕ УТИЛИТЫ
# =======================

def _get_weight(question: ChecklistQuestion) -> int:
    """
    Вес вопроса: поле .weight, затем question.meta['weight'], иначе 1.
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

def _is_yes(value: Optional[str]) -> bool:
    """Унификация «да»."""
    if value is None:
        return False
    return str(value).strip().lower() in YES_TOKENS

def _parse_scale(value: Optional[str]) -> int:
    """
    Шкала 1..5. Неверные/пустые → 1 (что даёт 0.0 после нормировки).
    """
    try:
        v = int(float(str(value).replace(",", ".").strip()))
        return max(SCALE_MIN, min(SCALE_MAX, v))
    except Exception:
        return SCALE_MIN  # 1 → 0.0

def compute_answer_score(db, ans: ChecklistAnswer) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Расчёт:
      - Шкала 1..5 → нормировка [0..1]: 1 => 0.0, 5 => 1.0
      - Да/Нет → 1.0/0.0
      - Балл = нормированное значение * вес
      - Итог = сумма(баллов); Макс = сумма(весов)
      - Процент = итог / максимум * 100
    """
    # Все вопросы по чек-листу
    questions = {q.id: q for q in db.query(ChecklistQuestion).filter_by(checklist_id=ans.checklist_id).all()}
    if not questions:
        return (None, None, None)

    q_answers = db.query(ChecklistQuestionAnswer).filter_by(answer_id=ans.id).all()
    if not q_answers:
        return (None, None, None)

    total_w = 0.0
    got = 0.0

    for qa in q_answers:
        q = questions.get(qa.question_id)
        if not q or q.type not in ("yesno", "scale"):
            continue

        w = float(_get_weight(q))
        total_w += w

        if q.type == "yesno":
            v_norm = 1.0 if _is_yes(qa.response_value) else 0.0
        else:  # scale
            v = _parse_scale(qa.response_value)         # 1..5
            v_norm = (v - SCALE_MIN) / float(SCALE_MAX - SCALE_MIN)  # 1 -> 0.0, 5 -> 1.0

        got += v_norm * w

    if total_w == 0:
        return (None, None, None)

    percent = round(got / total_w * 100, 1)
    return (round(got, 2), round(total_w, 2), percent)

# =======================
#    UI ВСПОМОГАТЕЛЬНЫЕ
# =======================

def _chip(text: str):
    st.markdown(
        f"""<span style="display:inline-block;padding:2px 8px;border-radius:999px;
        background:rgba(0,0,0,.05);font-size:11px;margin-right:6px;white-space:nowrap;">{text}</span>""",
        unsafe_allow_html=True,
    )

def _render_question_block_compact(q: ChecklistQuestion, qa: ChecklistQuestionAnswer, db_session, bot_token: Optional[str]):
    """
    Компактный рендер вопроса/ответа (минимум отступов).
    """
    weight = _get_weight(q)
    # Заголовок
    st.markdown(f"**{(q.order or 0)}. {q.text}**")
    cols = st.columns([0.70, 0.30])

    with cols[0]:
        if q.type == "yesno":
            if _is_yes(qa.response_value):
                _chip("ДА")
                st.progress(100)
            else:
                _chip("НЕТ/—")
                st.progress(0)
        elif q.type == "scale":
            v = _parse_scale(qa.response_value)  # 1..5
            v_norm = (v - SCALE_MIN) / float(SCALE_MAX - SCALE_MIN)
            st.progress(int(round(v_norm * 100)))
            _chip(f"{v}/{SCALE_MAX}  ·  {v_norm:.2f}")
        else:
            # Текстовые/прочие
            val = qa.response_value if (qa.response_value not in (None, "")) else "—"
            st.markdown(f"> {val}")

        # Комментарий
        if qa.comment:
            st.caption(f"Комментарий: {qa.comment}")

        # Фото — через единый резолвер
        local_path = ensure_local_photo(qa, db_session=db_session, bot_token=bot_token)
        if local_path and os.path.exists(local_path):
            st.image(local_path, caption="Фото", use_column_width=True)
        else:
            if qa.photo_path:
                st.caption(f"Источник: `{qa.photo_path}`")
            else:
                st.caption("Фото отсутствует")

    with cols[1]:
        if q.type in ("yesno", "scale"):
            _chip(f"вес {weight}")
        if getattr(q, "require_photo", False):
            _chip("фото обяз.")
        if getattr(q, "require_comment", False):
            _chip("коммент обяз.")

def _answers_df_for_all(db: Session) -> pd.DataFrame:
    """
    Плоский DF по всем ответам: score/max/percent, дата/чек-лист/пользователь.
    """
    answers = db.query(ChecklistAnswer).order_by(ChecklistAnswer.submitted_at.desc()).all()
    if not answers:
        return pd.DataFrame()

    rows = []
    for ans in answers:
        user = db.query(User).get(ans.user_id)
        checklist = db.query(Checklist).get(ans.checklist_id)
        score, max_score, percent = compute_answer_score(db, ans)
        rows.append({
            "answer_id": ans.id,
            "user": user.name if user else f"user_id={ans.user_id}",
            "checklist_id": ans.checklist_id,
            "checklist": checklist.name if checklist else f"checklist_id={ans.checklist_id}",
            "submitted_at": ans.submitted_at,
            "score": score,
            "max_score": max_score,
            "percent": percent,
        })
    df = pd.DataFrame(rows)
    if not df.empty and "submitted_at" in df.columns:
        df["date"] = pd.to_datetime(df["submitted_at"]).dt.date
    return df

# =======================
#        UI ВКЛАДКИ
# =======================

def reports_tab(company_id=None):
    st.title("📊 Отчёты по чек-листам")

    # -------- Автосинхронизация локальных фото при загрузке --------
    auto_updated = sync_local_photos_from_folder()
    if auto_updated:
        st.caption(f"🔄 Обновлено локальных ссылок на фото: {auto_updated}")

    # -------- Кнопка принудительного обновления (бот + ресинк) --------
    # ⚠️ желательно перенести токен в .env и доставать из config
    if st.button("🔁 Обновить изображения (скачать из Telegram + пересканировать папку)"):
        with st.spinner("Загрузка фото через бота..."):
            count, errors = download_photos_via_bot(BOT_TOKEN)
        resynced = sync_local_photos_from_folder()
        st.success(f"Скачано: {count}, ошибок: {errors}. Локально обновлено: {resynced}.")
        st.rerun()

    db = SessionLocal()   # именно скобки!
    df = _answers_df_for_all(db)


    # =======================
    #  СВОДКА ПО ВСЕМ ЧЕК-ЛИСТАМ
    # =======================
    st.markdown("### 📈 Общая сводка по всем чек-листам")

    df_all = _answers_df_for_all(db)
    if df_all.empty:
        st.info("Нет ответов по чек-листам.")
        db.close()
        return

    # KPI
    total_answers = len(df_all)
    avg_percent = round(df_all["percent"].dropna().mean(), 1) if "percent" in df_all else None
    unique_users = df_all["user"].nunique()
    unique_checklists = df_all["checklist"].nunique()

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Всего ответов", total_answers)
    k2.metric("Средняя оценка", f"{avg_percent}%" if avg_percent is not None else "—")
    k3.metric("Сотрудников участвовало", unique_users)
    k4.metric("Чек-листов", unique_checklists)

    # Таблица: средний % и количество по чек-листам
    per_cl = (
        df_all.groupby("checklist", as_index=False)
        .agg(avg_percent=("percent", "mean"), cnt=("answer_id", "count"))
        .sort_values(["avg_percent", "cnt"], ascending=[False, False])
    )
    per_cl["avg_percent"] = per_cl["avg_percent"].round(1)

    # Показ — с «человеческими» заголовками
    per_cl_show = per_cl.rename(columns={"avg_percent": "Средний %", "cnt": "Ответов"})
    st.dataframe(per_cl_show, use_container_width=True, hide_index=True)

    # Графики (экспериментально)
    st.markdown("#### Графики")
    g1, g2 = st.columns(2)

    with g1:
        st.caption("Средняя оценка, % по чек-листам")
        if not per_cl.empty:
            chart_df = per_cl.set_index("checklist")[["avg_percent"]]  # <-- реальное имя колонки
            st.bar_chart(chart_df)
        else:
            st.write("Нет данных для графика.")

    with g2:
        st.caption("Количество прохождений по чек-листам")
        if not per_cl.empty:
            chart_cnt = per_cl.set_index("checklist")[["cnt"]]  # <-- реальное имя колонки
            st.bar_chart(chart_cnt)
        else:
            st.write("Нет данных для графика.")

    # Тренд по дням (средний %)
    trend = (
        df_all.dropna(subset=["percent"])
        .groupby(["date"], as_index=False)
        .agg(avg_percent=("percent", "mean"))
        .sort_values("date")
    )
    if not trend.empty:
        trend["avg_percent"] = trend["avg_percent"].round(1)
        st.caption("Тренд средней оценки по дням")
        trend_chart = trend.set_index("date")[["avg_percent"]]
        st.line_chart(trend_chart)

    st.markdown("---")

    # =======================
    #   ДЕТАЛИ ПО ВЫБРАННОМУ ЧЕК-ЛИСТУ
    # =======================
    checklists = db.query(Checklist).all()
    cl_map = {cl.id: cl.name for cl in checklists}
    cl_options = ["Все чек-листы"] + [cl_map[cid] for cid in sorted(cl_map, key=lambda x: cl_map[x].lower())]
    selected_cl_name = st.selectbox("Выборочно: чек-лист", cl_options)

    base_q = db.query(ChecklistAnswer).order_by(ChecklistAnswer.submitted_at.desc())
    if selected_cl_name != "Все чек-листы":
        selected_cl_id = next((cid for cid, name in cl_map.items() if name == selected_cl_name), None)
        answers = base_q.filter(ChecklistAnswer.checklist_id == selected_cl_id).all()
    else:
        answers = base_q.all()

    if not answers:
        st.info("Нет ответов под выбранный фильтр.")
        db.close()
        return

    # Сводная таблица по выбранному срезу
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
                "Итог (баллы)": score if score is not None else "—",
                "Макс (весов)": max_score if max_score is not None else "—",
                "Оценка (%)": f"{percent}%" if percent is not None else "—",
            }
        )
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Детализация выбранного ответа
    ids = df["ID ответа"].tolist()
    if ids:
        selected_id = st.selectbox("Детали ответа (ID):", ids)
        if selected_id:
            ans = db.query(ChecklistAnswer).get(int(selected_id))
            user = db.query(User).get(ans.user_id)
            checklist = db.query(Checklist).get(ans.checklist_id)

            st.markdown(
                f"### {user.name if user else f'user_id={ans.user_id}'} — "
                f"{checklist.name if checklist else f'checklist_id={ans.checklist_id}'} "
                f"({ans.submitted_at.strftime('%Y-%m-%d %H:%M') if ans.submitted_at else '–'})"
            )

            q_answers = db.query(ChecklistQuestionAnswer).filter_by(answer_id=ans.id).all()

            for q_ans in q_answers:
                question = db.query(ChecklistQuestion).get(q_ans.question_id)
                if not question:
                    st.markdown(f"**Вопрос #{q_ans.question_id}**")
                    st.markdown(f"> {q_ans.response_value if q_ans.response_value else '—'}")
                    continue
                _render_question_block_compact(question, q_ans, db_session=db, bot_token=TOKEN)

            # Итог
            score, max_score, percent = compute_answer_score(db, ans)
            st.markdown("---")
            if percent is not None:
                st.metric("Итоговая оценка", f"{score} / {max_score}", delta=f"{percent}%")
                st.progress(int(round(percent)), text=f"{percent}%")
            else:
                st.caption("Для этого ответа нет оцениваемых вопросов (yes/no или шкала).")

    db.close()

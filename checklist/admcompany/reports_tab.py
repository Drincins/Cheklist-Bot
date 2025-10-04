import os
from typing import Dict, Optional, Tuple

import pandas as pd
import altair as alt
import streamlit as st
from sqlalchemy.orm import Session

from checklist.db.db import SessionLocal
from checklist.db.models import (
    Checklist,
    ChecklistAnswer,
    ChecklistQuestion,
    ChecklistQuestionAnswer,
    Department,
    User,
)
from checklist.db.models.user import user_department_access

# =======================
#     НАСТРОЙКИ / КОНСТАНТЫ
# =======================

SCALE_MIN = 1
SCALE_MAX = 5  # 1 = 0, 5 = 1

YES_TOKENS = {"да", "yes", "y", "true", "1", "ok", "✔", "✅", "пройдено", "завершено"}

MEDIA_DIR = "media"
FALLBACK_EXT = ".jpg"
os.makedirs(MEDIA_DIR, exist_ok=True)
BOT_TOKEN_ENV = os.getenv("TELEGRAM_BOT_TOKEN")


# =======================
#      ФОТО: УТИЛИТЫ
# =======================


def _is_local_image_path(value: Optional[str]) -> bool:
    if not value:
        return False
    return value.strip().lower().endswith((".jpg", ".jpeg", ".png"))


def _local_photo_path_for(answer_id: int) -> str:
    return os.path.join(MEDIA_DIR, f"qa_{answer_id}{FALLBACK_EXT}")


def ensure_local_photo(
    qa: ChecklistQuestionAnswer,
    db_session: Session,
    bot_token: Optional[str] = None,
) -> Optional[str]:
    """Гарантирует наличие локального фото для ответа qa, при необходимости скачивает из Telegram."""

    current_path = (qa.photo_path or "").strip()

    if _is_local_image_path(current_path) and os.path.exists(current_path):
        return current_path

    candidate = _local_photo_path_for(qa.id)
    if os.path.exists(candidate):
        if current_path != candidate:
            qa.photo_path = candidate
            try:
                db_session.commit()
            except Exception:
                db_session.rollback()
        return candidate

    if not _is_local_image_path(current_path) and current_path and bot_token:
        try:
            import asyncio
            from aiogram import Bot

            async def _download() -> None:
                bot = Bot(token=bot_token)
                file = await bot.get_file(current_path)
                await bot.download_file(file.file_path, destination=candidate)

            asyncio.run(_download())
            if os.path.exists(candidate):
                qa.photo_path = candidate
                try:
                    db_session.commit()
                except Exception:
                    db_session.rollback()
                return candidate
        except Exception as exc:  # pragma: no cover - логирование исключений
            print(f"[ensure_local_photo] download error for {current_path}: {exc}")

    return None


def download_photos_via_bot(token: str) -> Tuple[int, int]:
    """Скачивает фото по file_id из Telegram. Возвращает (скачано, ошибок)."""

    import asyncio
    from aiogram import Bot

    async def _inner() -> Tuple[int, int]:
        db = SessionLocal()
        try:
            bot = Bot(token=token)
            answers = db.query(ChecklistQuestionAnswer).all()
            downloaded, errors = 0, 0
            for qa in answers:
                current_path = (qa.photo_path or "").strip()
                if _is_local_image_path(current_path) and os.path.exists(current_path):
                    continue

                candidate = _local_photo_path_for(qa.id)
                if os.path.exists(candidate):
                    if current_path != candidate:
                        qa.photo_path = candidate
                        db.commit()
                    continue

                if not _is_local_image_path(current_path) and current_path:
                    try:
                        file = await bot.get_file(current_path)
                        await bot.download_file(file.file_path, destination=candidate)
                        if os.path.exists(candidate):
                            qa.photo_path = candidate
                            db.commit()
                            downloaded += 1
                    except Exception as exc:  # pragma: no cover - логирование исключений
                        errors += 1
                        print(f"[download_photos_via_bot] {current_path} -> error: {exc}")
            return downloaded, errors
        finally:
            db.close()

    return asyncio.run(_inner())


def sync_local_photos_from_folder() -> int:
    """Синхронизирует файлы media/qa_<id>.jpg с записями в БД."""

    db = SessionLocal()
    try:
        updated = 0
        files = [
            f
            for f in os.listdir(MEDIA_DIR)
            if f.startswith("qa_") and f.lower().endswith((".jpg", ".jpeg", ".png"))
        ]
        if not files:
            return 0

        paths_by_answer: Dict[int, str] = {}
        for filename in files:
            stem, _ = os.path.splitext(filename)
            parts = stem.split("_")
            if len(parts) == 2 and parts[1].isdigit():
                paths_by_answer[int(parts[1])] = os.path.join(MEDIA_DIR, filename)

        if not paths_by_answer:
            return 0

        answers = (
            db.query(ChecklistQuestionAnswer)
            .filter(ChecklistQuestionAnswer.id.in_(paths_by_answer.keys()))
            .all()
        )
        for qa in answers:
            desired = paths_by_answer.get(qa.id)
            if not desired:
                continue
            current_path = (qa.photo_path or "").strip()
            if (
                not _is_local_image_path(current_path)
                or current_path != desired
                or (current_path and not os.path.exists(current_path))
            ):
                qa.photo_path = desired
                updated += 1
        if updated:
            db.commit()
        return updated
    finally:
        db.close()


# =======================
#   ПОДРАЗДЕЛЕНИЯ
# =======================


def _accessible_departments(db: Session, company_id: Optional[int]) -> list[Department]:
    if not company_id:
        return []

    base_query = (
        db.query(Department)
        .filter(Department.company_id == company_id)
        .order_by(Department.name.asc())
    )

    if st.session_state.get("is_superadmin"):
        return base_query.all()

    user_id = st.session_state.get("user_id")
    if user_id:
        user = db.query(User).get(int(user_id))
        if user and getattr(user, "departments", None):
            deps = [d for d in user.departments if d.company_id == company_id]
            if deps:
                return sorted(deps, key=lambda d: d.name.lower())

    return base_query.all()


# =======================
#   СКОРИНГ
# =======================


def _resolve_weight(raw_weight: Optional[int], raw_meta: Optional[dict]) -> float:
    if raw_weight is not None:
        return float(raw_weight)
    if isinstance(raw_meta, dict):
        candidate = raw_meta.get("weight")
        if candidate is not None:
            try:
                return float(candidate)
            except (TypeError, ValueError):
                pass
    return 1.0


def _is_yes(value: Optional[str]) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in YES_TOKENS


def _parse_scale(value: Optional[str]) -> int:
    try:
        parsed = int(float(str(value).replace(",", ".").strip()))
    except (TypeError, ValueError):
        parsed = SCALE_MIN
    return max(SCALE_MIN, min(SCALE_MAX, parsed))


def _compute_scores_map(rows) -> Dict[int, Tuple[Optional[float], Optional[float], Optional[float]]]:
    totals: Dict[int, Dict[str, float]] = {}
    for row in rows:
        bucket = totals.setdefault(row.answer_id, {"score": 0.0, "weight": 0.0})
        if row.type not in ("yesno", "scale"):
            continue
        weight = _resolve_weight(row.weight, row.meta)
        bucket["weight"] += weight

        if row.type == "yesno":
            value = 1.0 if _is_yes(row.response_value) else 0.0
        else:
            scale_value = _parse_scale(row.response_value)
            value = (scale_value - SCALE_MIN) / float(SCALE_MAX - SCALE_MIN)
        bucket["score"] += value * weight

    scores: Dict[int, Tuple[Optional[float], Optional[float], Optional[float]]] = {}
    for answer_id, data in totals.items():
        total_weight = data["weight"]
        if total_weight <= 0:
            scores[answer_id] = (None, None, None)
            continue
        score_value = round(data["score"], 2)
        max_value = round(total_weight, 2)
        percent_value = round(data["score"] / total_weight * 100, 1)
        scores[answer_id] = (score_value, max_value, percent_value)
    return scores


@st.cache_data(ttl=60)
def _answers_df_for_all(company_id: Optional[int]) -> pd.DataFrame:
    """Выбирает все ответы и возвращает плоский DataFrame с оценками и подразделениями."""

    db = SessionLocal()
    try:
        base_query = (
            db.query(
                ChecklistAnswer.id.label("answer_id"),
                ChecklistAnswer.submitted_at.label("submitted_at"),
                ChecklistAnswer.checklist_id.label("checklist_id"),
                Checklist.name.label("checklist_name"),
                Checklist.company_id.label("company_id"),
                User.id.label("user_id"),
                User.name.label("user_name"),
                Department.id.label("department_id"),
                Department.name.label("department_name"),
            )
            .join(User, ChecklistAnswer.user_id == User.id)
            .join(Checklist, ChecklistAnswer.checklist_id == Checklist.id)
            .outerjoin(user_department_access, user_department_access.c.user_id == User.id)
            .outerjoin(Department, user_department_access.c.department_id == Department.id)
        )

        if company_id is not None:
            base_query = base_query.filter(Checklist.company_id == company_id)

        answer_rows = base_query.order_by(ChecklistAnswer.submitted_at.desc()).all()
        if not answer_rows:
            return pd.DataFrame()

        answer_info: Dict[int, Dict[str, object]] = {}
        departments_by_answer: Dict[int, set] = {}
        for row in answer_rows:
            answer_info.setdefault(
                row.answer_id,
                {
                    "answer_id": row.answer_id,
                    "submitted_at": row.submitted_at,
                    "checklist_id": row.checklist_id,
                    "checklist": row.checklist_name,
                    "user_id": row.user_id,
                    "user": row.user_name,
                },
            )
            if row.department_id:
                entries = departments_by_answer.setdefault(row.answer_id, set())
                entries.add((row.department_id, row.department_name))

        answer_ids = list(answer_info.keys())

        qa_rows = (
            db.query(
                ChecklistQuestionAnswer.answer_id,
                ChecklistQuestionAnswer.response_value,
                ChecklistQuestion.type,
                ChecklistQuestion.weight,
                ChecklistQuestion.meta,
            )
            .join(ChecklistQuestion, ChecklistQuestionAnswer.question_id == ChecklistQuestion.id)
            .filter(ChecklistQuestionAnswer.answer_id.in_(answer_ids))
            .all()
        )

        scores_map = _compute_scores_map(qa_rows)

        records = []
        for answer_id, data in answer_info.items():
            departments = sorted(departments_by_answer.get(answer_id, set()))
            department_ids = tuple(dep_id for dep_id, _ in departments)
            department_names = ", ".join(dep_name for _, dep_name in departments)

            score, max_score, percent = scores_map.get(answer_id, (None, None, None))

            record = {
                **data,
                "score": score,
                "max_score": max_score,
                "percent": percent,
                "department_ids": department_ids,
                "department_names": department_names,
            }
            records.append(record)

        df = pd.DataFrame(records)
        if not df.empty and "submitted_at" in df.columns:
            df["submitted_at"] = pd.to_datetime(df["submitted_at"])
            df["date"] = df["submitted_at"].dt.date
        return df
    finally:
        db.close()


# =======================
#        UI ВКЛАДКИ
# =======================


def reports_tab(company_id: Optional[int] = None) -> None:
    """Главная страница с отчётами в Streamlit."""

    st.title("Отчеты по чек-листам")

    col_sync, col_download = st.columns(2)
    with col_sync:
        if st.button("Сканировать папку media", use_container_width=True):
            with st.spinner("Проверяем папку media..."):
                updated = sync_local_photos_from_folder()
            if updated:
                st.success(f"Обновлено путей: {updated}")
            else:
                st.info("Новых файлов не найдено.")

    with col_download:
        if st.button("Обновить фото через Telegram", use_container_width=True):
            bot_token = BOT_TOKEN_ENV or os.getenv("TELEGRAM_BOT_TOKEN")
            if not bot_token:
                st.warning("Токен Telegram бота не задан. Укажите TELEGRAM_BOT_TOKEN в .env.")
            else:
                with st.spinner("Загружаем фотографии через бота..."):
                    downloaded, errors = download_photos_via_bot(bot_token)
                resynced = sync_local_photos_from_folder()
                st.success(
                    f"Скачано: {downloaded}, ошибок: {errors}. Обновлено локальных путей: {resynced}."
                )
                st.experimental_rerun()

    df_all = _answers_df_for_all(company_id)
    if df_all.empty:
        st.info("Нет ответов по чек-листам.")
        return

    with SessionLocal() as db:
        departments = _accessible_departments(db, company_id)

    department_options = [(dep.id, dep.name) for dep in departments]
    has_answers_without_department = df_all["department_ids"].apply(lambda ids: not ids).any()
    if has_answers_without_department:
        department_options.append((None, "Без подразделения"))

    if not department_options:
        st.info("Нет доступных подразделений для просмотра отчета.")
        return

    default_department_id = st.session_state.get("reports_selected_department_id")
    option_ids = [identifier for identifier, _ in department_options]
    if default_department_id not in option_ids:
        default_department_id = department_options[0][0]

    default_index = option_ids.index(default_department_id)
    selected_id, selected_name = st.selectbox(
        "Подразделение",
        options=department_options,
        index=default_index,
        format_func=lambda option: option[1],
        key="reports_department_select",
    )
    st.session_state["reports_selected_department_id"] = selected_id

    def _belongs_to_department(ids: tuple[int, ...]) -> bool:
        if not ids:
            return selected_id is None
        if selected_id is None:
            return False
        return selected_id in ids

    df_dept = df_all[df_all["department_ids"].apply(_belongs_to_department)].copy()

    st.subheader(f"Подразделение: {selected_name}")

    if df_dept.empty:
        st.info("Нет данных по выбранному подразделению.")
        return

    df_dept.sort_values("submitted_at", inplace=True)

    total_answers = len(df_dept)
    avg_percent_value = (
        round(df_dept["percent"].dropna().mean(), 1)
        if "percent" in df_dept and not df_dept["percent"].dropna().empty
        else None
    )
    unique_users = df_dept["user"].nunique()
    unique_checklists = df_dept["checklist"].nunique()

    st.write(f"Ответов: {total_answers}")
    st.write(
        "Средний %: "
        + (f"{avg_percent_value}%" if avg_percent_value is not None else "—")
    )
    st.write(f"Сотрудников: {unique_users}")
    st.write(f"Чек-листов: {unique_checklists}")

    st.markdown("---")
    
    filters = st.columns((2, 2, 3))
    checklists = ["Все чек-листы"] + sorted(
        df_dept["checklist"].dropna().unique().tolist()
    )
    selected_checklist = filters[0].selectbox(
        "Чек-лист",
        options=checklists,
        index=0,
        key="reports_checklist_filter",
    )
    users = ["Все сотрудники"] + sorted(
        df_dept["user"].dropna().unique().tolist()
    )
    selected_user = filters[1].selectbox(
        "Сотрудник",
        options=users,
        index=0,
        key="reports_user_filter",
    )
    
    min_date = df_dept["date"].min()
    max_date = df_dept["date"].max()
    start_date, end_date = None, None
    if pd.notna(min_date) and pd.notna(max_date):
        if isinstance(min_date, pd.Timestamp):
            min_date = min_date.date()
        if isinstance(max_date, pd.Timestamp):
            max_date = max_date.date()
        period_value = filters[2].date_input(
            "Период",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )
        if isinstance(period_value, tuple):
            start_date, end_date = period_value
        else:
            start_date = end_date = period_value
    
    df_filtered = df_dept.copy()
    if selected_checklist != "Все чек-листы":
        df_filtered = df_filtered[df_filtered["checklist"] == selected_checklist]
    if selected_user != "Все сотрудники":
        df_filtered = df_filtered[df_filtered["user"] == selected_user]
    if start_date and end_date:
        df_filtered = df_filtered[
            (df_filtered["date"] >= start_date) & (df_filtered["date"] <= end_date)
        ]
    
    if df_filtered.empty:
        st.info("Нет данных по выбранным фильтрам.")
        return
    
    percent_series = df_filtered["percent"].dropna()
    avg_percent_value = (
        round(percent_series.mean(), 1) if not percent_series.empty else None
    )
    best_percent = (
        round(percent_series.max(), 1) if not percent_series.empty else None
    )
    worst_percent = (
        round(percent_series.min(), 1) if not percent_series.empty else None
    )
    best_row = (
        df_filtered.loc[percent_series.idxmax()] if not percent_series.empty else None
    )
    worst_row = (
        df_filtered.loc[percent_series.idxmin()] if not percent_series.empty else None
    )
    
    metrics = st.columns(4)
    metrics[0].metric("Всего проверок", len(df_filtered))
    metrics[1].metric(
        "Средний %", f"{avg_percent_value}%" if avg_percent_value is not None else "—"
    )
    metrics[2].metric(
        "Лучший %", f"{best_percent}%" if best_percent is not None else "—"
    )
    metrics[3].metric(
        "Минимальный %", f"{worst_percent}%" if worst_percent is not None else "—"
    )
    
    summary_tab, trend_tab, details_tab = st.tabs(
        ["Сводка", "Динамика", "Детали"]
    )
    
    with summary_tab:
        if best_row is not None:
            st.markdown(
                f"**Лучший результат:** {best_row['percent']:.1f}% — {best_row['checklist']} ({best_row['user']})"
            )
        if worst_row is not None:
            st.markdown(
                f"**Минимальный результат:** {worst_row['percent']:.1f}% — {worst_row['checklist']} ({worst_row['user']})"
            )
    
        col_summary_left, col_summary_right = st.columns(2)
        grouped_checklists = (
            df_filtered.groupby("checklist", as_index=False)
            .agg(
                checks=("answer_id", "count"),
                avg_percent=("percent", "mean"),
            )
            .sort_values("avg_percent", ascending=False)
        )
        if not grouped_checklists.empty:
            grouped_checklists["avg_percent"] = grouped_checklists["avg_percent"].round(1)
            grouped_checklists.rename(
                columns={
                    "checklist": "Чек-лист",
                    "checks": "Проверок",
                    "avg_percent": "Средний %",
                },
                inplace=True,
            )
            col_summary_left.write("По чек-листам")
            col_summary_left.dataframe(
                grouped_checklists, use_container_width=True, hide_index=True
            )
    
        grouped_users = (
            df_filtered.groupby("user", as_index=False)
            .agg(
                checks=("answer_id", "count"),
                avg_percent=("percent", "mean"),
            )
            .sort_values("avg_percent", ascending=False)
        )
        if not grouped_users.empty:
            grouped_users["avg_percent"] = grouped_users["avg_percent"].round(1)
            grouped_users.rename(
                columns={
                    "user": "Сотрудник",
                    "checks": "Проверок",
                    "avg_percent": "Средний %",
                },
                inplace=True,
            )
            col_summary_right.write("По сотрудникам")
            col_summary_right.dataframe(
                grouped_users, use_container_width=True, hide_index=True
            )
    
        if avg_percent_value is not None:
            st.progress(min(max(avg_percent_value / 100, 0.0), 1.0))
    
    with trend_tab:
        trend_df = (
            df_filtered.groupby("date", as_index=False)
            .agg(
                avg_percent=("percent", "mean"),
                checks=("answer_id", "count"),
            )
            .sort_values("date")
        )
        if not trend_df.empty:
            trend_df["avg_percent"] = trend_df["avg_percent"].round(1)
            trend_df["date"] = pd.to_datetime(trend_df["date"])
            line = (
                alt.Chart(trend_df)
                .mark_line(point=True)
                .encode(
                    x=alt.X("date:T", title="Дата"),
                    y=alt.Y(
                        "avg_percent:Q",
                        title="Средний %",
                        scale=alt.Scale(domain=[0, 100]),
                    ),
                    tooltip=[
                        alt.Tooltip("date:T", title="Дата"),
                        alt.Tooltip("avg_percent:Q", title="Средний %"),
                        alt.Tooltip("checks:Q", title="Проверок"),
                    ],
                )
            )
            bars = (
                alt.Chart(trend_df)
                .mark_bar(opacity=0.3)
                .encode(
                    x="date:T",
                    y=alt.Y("checks:Q", title="Проверок"),
                    tooltip=[
                        alt.Tooltip("date:T", title="Дата"),
                        alt.Tooltip("checks:Q", title="Проверок"),
                    ],
                )
            )
            st.altair_chart(
                alt.layer(bars, line).resolve_scale(y="independent"),
                use_container_width=True,
            )
        else:
            st.info("Недостаточно данных для графика.")
    
    with details_tab:
        detail_cols = [
            "submitted_at",
            "checklist",
            "user",
            "percent",
            "score",
            "max_score",
            "department_names",
        ]
        display_df = df_filtered[detail_cols].copy()
        display_df["submitted_at"] = pd.to_datetime(display_df["submitted_at"])
        display_df["submitted_at"] = display_df["submitted_at"].dt.strftime("%d.%m.%Y %H:%M")
        display_df["percent"] = display_df["percent"].apply(
            lambda x: round(x, 1) if pd.notna(x) else x
        )
        display_df.rename(
            columns={
                "submitted_at": "Время сдачи",
                "checklist": "Чек-лист",
                "user": "Сотрудник",
                "percent": "Результат %",
                "score": "Баллы",
                "max_score": "Макс. баллы",
                "department_names": "Подразделения",
            },
            inplace=True,
        )
        st.dataframe(display_df, use_container_width=True, hide_index=True)

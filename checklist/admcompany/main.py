import streamlit as st
from pathlib import Path
from typing import Optional, List, Dict
from sqlalchemy.orm import joinedload

from checklist.db.db import SessionLocal
from checklist.db.models import User, Position, Checklist, Department
from checklist.admcompany.departments_main import departments_main
from checklist.admcompany.employees_main import employees_main
from checklist.admcompany.checklists_main import checklists_main
from checklist.admcompany.reports_tab import reports_tab, _answers_df_for_all
from streamlit_cookies_manager import EncryptedCookieManager


# ----------------------------
#   НАВИГАЦИЯ
# ----------------------------
MENU_ITEMS = [
    ("Подразделения", departments_main),
    ("Сотрудники и должности", employees_main),
    ("Чек-листы", checklists_main),
    ("Отчеты", reports_tab),
]


# ----------------------------
#   АВТОРИЗАЦИЯ / СЕССИЯ
# ----------------------------
def _logout(cookies: Optional[EncryptedCookieManager]) -> None:
    """Сброс авторизации и куков."""
    st.session_state.auth = False
    st.session_state.is_company_admin = False
    st.session_state.is_superadmin = False
    st.session_state.admin_company_id = None
    st.session_state.user_id = None
    st.session_state.user_name = "Гость"
    st.session_state.user_role = None

    if cookies is not None:
        for key in (
            "auth",
            "is_superadmin",
            "is_company_admin",
            "admin_company_id",
            "user_id",
            "user_name",
            "user_role",
        ):
            cookies[key] = ""
        cookies.save()

    st.rerun()


# ----------------------------
#   ДАННЫЕ ДЛЯ ГЛАВНОЙ
# ----------------------------
def _get_department_summaries(company_id: int) -> List[Dict[str, object]]:
    """
    Сводка по каждому подразделению.
    Считаем внутри одной сессии (joinedload), чтобы не ловить DetachedInstanceError.
    """
    with SessionLocal() as db:
        deps = (
            db.query(Department)
            .filter(Department.company_id == company_id)
            .options(
                joinedload(Department.users)
                .joinedload(User.position)
                .joinedload(Position.checklists)
            )
            .order_by(Department.name.asc())
            .all()
        )

        summaries: List[Dict[str, object]] = []
        for d in deps:
            users = d.users or []
            pos_ids = set()
            chk_ids = set()

            for u in users:
                if u.position_id:
                    pos_ids.add(u.position_id)
                    pos = u.position
                    if pos and getattr(pos, "checklists", None):
                        for c in pos.checklists:
                            chk_ids.add(c.id)

            summaries.append({
                "id": d.id,
                "Подразделение": d.name,
                "Сотрудников": len(users),
                "Должностей": len(pos_ids),
                "Чек-листов": len(chk_ids),
                "Средний балл": "—",  # ниже подставим из отчёта
            })

    # средний балл из отчёта (вне ORM-сессии)
    avg_map: Dict[int, float] = {}
    try:
        df = _answers_df_for_all(company_id)
        if not df.empty and "department_ids" in df.columns:
            rows = []
            for _, r in df.iterrows():
                ids = r.get("department_ids")
                if isinstance(ids, (list, tuple)):
                    for did in ids:
                        rows.append({"dep_id": did, "percent": r.get("percent")})
            if rows:
                import pandas as _pd
                t = _pd.DataFrame(rows).dropna(subset=["percent"])
                if not t.empty:
                    avg_map = t.groupby("dep_id")["percent"].mean().round(1).to_dict()
    except Exception:
        avg_map = {}

    for item in summaries:
        item["Средний балл"] = avg_map.get(item["id"], "—")

    return summaries


# ----------------------------
#   UI HELPERS (без CSS)
# ----------------------------
def _score_emoji(val: Optional[float]) -> str:
    if val is None:
        return "➖"
    try:
        p = float(val)
    except Exception:
        return "➖"
    if p < 75:
        return "😟"
    elif p < 90:
        return "😐"
    else:
        return "😊"


def _render_cards_native(items: List[Dict[str, object]], cols_per_row: int = 2) -> None:
    """
    Нативные карточки Streamlit:
    - Внешняя карточка: st.container(border=True)
    - Внутри: три мини-бокса (border=True) с уменьшенными числами
    - Заголовок по центру, крупнее
    - Подпись среднего балла над прогресс-баром
    """
    if not items:
        st.info("Подразделений нет.")
        return

    cols_per_row = max(1, cols_per_row)

    for i, it in enumerate(items):
        if i % cols_per_row == 0:
            row = st.columns(cols_per_row)
        col = row[i % cols_per_row]
        with col:
            with st.container(border=True):
                # Заголовок по центру, немного крупнее
                st.markdown(
                    f"<div style='text-align:center; font-size:1.15rem; font-weight:700; margin-bottom:8px;'>"
                    f"{it['Подразделение']}"
                    f"</div>",
                    unsafe_allow_html=True,
                )

                # Три мини-бокса с рамкой и уменьшенным шрифтом чисел
                c1, c2, c3 = st.columns(3)
                with c1:
                    with st.container(border=True):
                        st.markdown(
                            "<div style='font-size:0.9rem; color:#9aa0a6;'>Сотрудники</div>"
                            f"<div style='font-size:1.35rem; font-weight:700;'>{it['Сотрудников']}</div>",
                            unsafe_allow_html=True,
                        )
                with c2:
                    with st.container(border=True):
                        st.markdown(
                            "<div style='font-size:0.9rem; color:#9aa0a6;'>Должности</div>"
                            f"<div style='font-size:1.35rem; font-weight:700;'>{it['Должностей']}</div>",
                            unsafe_allow_html=True,
                        )
                with c3:
                    with st.container(border=True):
                        st.markdown(
                            "<div style='font-size:0.9rem; color:#9aa0a6;'>Чек-листов</div>"
                            f"<div style='font-size:1.35rem; font-weight:700;'>{it['Чек-листов']}</div>",
                            unsafe_allow_html=True,
                        )

                # Подпись среднего балла — над прогресс-баром
                val = it.get("Средний балл")
                try:
                    p = float(val)
                except Exception:
                    p = None

                if p is not None:
                    st.markdown(
                        f"<div style='font-size:1.15rem; font-weight:700; margin:6px 0 6px 0;'>"
                        f"Средний балл: {p}% "
                        f"<span style='font-size:1.5rem; line-height:1;'>{_score_emoji(p)}</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    st.progress(int(round(max(0, min(100, p)))))
                else:
                    st.markdown(
                        "<div style='font-size:1.15rem; font-weight:700; margin:6px 0 6px 0;'>"
                        "Средний балл: — "
                        f"<span style='font-size:1.5rem; line-height:1;'>{_score_emoji(None)}</span>"
                        "</div>",
                        unsafe_allow_html=True,
                    )


# ----------------------------
#   ГЛАВНАЯ
# ----------------------------
def _render_home(company_id: Optional[int]) -> None:
    """
    Главная: Главная + локальный логотип (logo.png рядом с app.py),
    ниже — карточки подразделений (2 в ряд) без кастомного CSS.
    """
    # Заголовок + логотип
    logo_path = Path("logo.png")
    if logo_path.exists():
        c1, c2 = st.columns([1, 8])
        with c1:
            st.image(str(logo_path), width=560)  # крупный логотип
        with c2:
            st.markdown("## ")
    else:
        st.markdown("## ")

    if company_id is None:
        st.info("Выберите компанию, чтобы увидеть статистику.")
        return

    summaries = _get_department_summaries(company_id)
    _render_cards_native(summaries, cols_per_row=2)


# ----------------------------
#   ROOT VIEW (сайдбар и маршрутизация)
# ----------------------------
def company_admin_dashboard(
    company_id: Optional[int],
    cookies: Optional[EncryptedCookieManager] = None,
) -> None:
    user_name = st.session_state.get("user_name", "Гость")
    user_role = st.session_state.get("user_role", "Без роли")
    current = st.session_state.get("main_menu", "Главная")

    with st.sidebar:
        st.markdown(f"**👤 {user_name}**")
        st.caption(f"Роль: {user_role}")
        if st.button("Выйти", use_container_width=True):
            _logout(cookies)

        st.markdown("---")
        nav_items = [("Главная", None)] + MENU_ITEMS
        for label, _ in nav_items:
            if st.button(
                label,
                key=f"nav_btn_{label}",
                use_container_width=True,
                disabled=(current == label),
            ):
                st.session_state["main_menu"] = label
                st.rerun()

    current = st.session_state.get("main_menu", "Главная")
    if current == "Главная":
        _render_home(company_id)
    else:
        for label, render_fn in MENU_ITEMS:
            if label == current and render_fn is not None:
                render_fn(company_id)
                break

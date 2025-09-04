from http import cookies
import streamlit as st
from sqlalchemy.orm import joinedload

from checklist.db.db import SessionLocal
from checklist.db.models import User, Position, Role

from checklist.admcompany.employees_main import employees_main
from checklist.admcompany.departments_main import departments_main
from checklist.admcompany.checklists_main import checklists_main
from checklist.admcompany.reports_tab import reports_tab
from streamlit_cookies_manager import EncryptedCookieManager

def _ensure_user_role():
    """
    Страховка: если по какой-то причине роль не в сессии — подтянем её из БД.
    Не ломаем UI даже при пустых cookies.
    """
    if st.session_state.get("is_superadmin"):
        st.session_state.setdefault("user_role", "Главный администратор")
        return

    if not st.session_state.get("user_role"):
        uid = st.session_state.get("user_id")
        if uid:
            db = SessionLocal()
            try:
                u = (
                    db.query(User)
                    .options(joinedload(User.position).joinedload(Position.role))
                    .get(uid)
                )
                st.session_state["user_role"] = (
                    u.position.role.name if u and u.position and u.position.role else "employee"
                )
            finally:
                db.close()
        else:
            # дефолт на случай полностью пустой сессии
            st.session_state["user_role"] = "employee"


def company_admin_dashboard(company_id):
    # гарантированно восстанавливаем роль (если надо)
    _ensure_user_role()

    st.title("👨‍💼 Панель администратора компании")

    # --- Сайдбар: профиль, меню, кнопка выхода внизу ---
    with st.sidebar:
        # CSS, чтобы кнопку «Выйти» прижать к низу сайдбара
        st.markdown("""
        <style>
        div[data-testid="stSidebar"] div.block-container {
            display:flex; flex-direction:column; height:100%;
        }
        .logout-holder { margin-top:auto; padding-top:.5rem; }
        .logout-holder button { background-color:#FFA500 !important; color:#000 !important; border:0 !important; }
        </style>
        """, unsafe_allow_html=True)

        user_name = st.session_state.get("user_name", "Гость")
        user_role = st.session_state.get("user_role", "Не определено")
        st.markdown(f"{user_role}")
        st.markdown("👤"f"**{user_name}**")
        st.markdown("---")  # Разделитель перед меню

        menu = st.radio(
            "Меню",
            [
                "Подразделения",
                "Сотрудники и должности",
                "Чек-листы",
                "Отчёты",
            ],
            key="main_menu",
        )

    # --- Кнопка выхода (в самом низу сайдбара) ---
    with st.sidebar:
        st.markdown("---")
        if st.button("🔒 Выйти", key="logout_btn_sidebar"):
            # чистим session_state
            st.session_state.auth = False
            st.session_state.is_company_admin = False
            st.session_state.is_superadmin = False
            st.session_state.admin_company_id = None
            st.session_state.user_id = None
            st.session_state.user_name = "Гость"
            st.session_state.user_role = None

            # чистим cookies, если доступны (cookies объявлены в app.py)
            try:
                cookies  # noqa: just check name exists
                for k in ("auth", "is_superadmin", "is_company_admin",
                        "admin_company_id", "user_id", "user_name", "user_role"):
                    cookies[k] = ""
                cookies.save()
            except NameError:
                pass

            st.rerun()


    # --- Контент по выбранному пункту меню ---
    if menu == "Сотрудники и должности":
        employees_main(company_id)
    elif menu == "Чек-листы":
        checklists_main(company_id)
    elif menu == "Отчёты":
        reports_tab(company_id)
    elif menu == "Подразделения":
        departments_main(company_id)

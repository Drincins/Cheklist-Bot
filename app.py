import os
import csv
import streamlit as st
from dotenv import load_dotenv

from checklist.db.db import SessionLocal, init_db
from checklist.db.models import User, Position, Role
from checklist.admcompany.main import company_admin_dashboard
from checklist.superadmintab import main_superadmin

import bcrypt
from sqlalchemy.orm import joinedload

# ——— cookies
from streamlit_cookies_manager import EncryptedCookieManager


# =========================
#   UI SETTINGS (CSV)
# =========================
def _load_ui_settings(path: str = "ui_settings.csv") -> dict:
    cfg = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                k = (row.get("key") or "").strip()
                v = (row.get("value") or "").strip()
                if k:
                    cfg[k] = v
    return cfg


_ui = _load_ui_settings()
_primary = _ui.get("primaryColor", "#D87E24")
_bg = _ui.get("backgroundColor", "#1E1E1E")
_sb_bg = _ui.get("secondaryBackgroundColor", "#2C2C2C")
_txt = _ui.get("textColor", "#FFFFFF")
_font_url = _ui.get(
    "font_url",
    "https://fonts.googleapis.com/css2?family=Comfortaa:wght@400;600&display=swap",
)
_font = _ui.get("font_family", "Comfortaa")
_font_size = int(_ui.get("font_size_px", "14") or 14)
_wide = _ui.get("wide_mode", "true").lower() in ("1", "true", "yes", "y")

# Page config (wide/centered)
st.set_page_config(layout="wide" if _wide else "centered")

# Глобальные стили: шрифт, цвета, фон сайдбара, размер шрифта, кнопки
st.markdown(
    f"""
<style>
@import url('{_font_url}');

html, body, .stApp, [class*="css"]
  font-family: '{_font}', sans-serif !important;
  font-size: {_font_size}px !important;
  color: {_txt} !important;
  background: {_bg} !important;
}}
section[data-testid="stSidebar"] {{
  background-color: {_sb_bg} !important;
}}
/* Primary-кнопки */
div.stButton > button, button[kind="primary"] {{
  background-color: {_primary} !important;
  color: #000 !important;
  border: 0 !important;
}}
/* Заголовки — немного жирнее */
h1, h2, h3, h4, h5, h6 {{
  font-weight: 600 !important;
}}
</style>
""",
    unsafe_allow_html=True,
)


# =========================
#   ИНИЦИАЛИЗАЦИЯ
# =========================
load_dotenv()
SA_LOGIN = os.getenv("SUPERADMIN_LOGIN")
SA_PASS = os.getenv("SUPERADMIN_PASSWORD")
init_db()

# ——— Настройка cookies
cookies = EncryptedCookieManager(prefix="checklist_", password="SECRET_COOKIE_PASSWORD_2024")
if not cookies.ready():
    st.stop()

# ——— Инициализация session_state из cookies
if "auth" not in st.session_state:
    st.session_state.auth = cookies.get("auth") == "1"
    st.session_state.is_company_admin = cookies.get("is_company_admin") == "1"
    st.session_state.is_superadmin = cookies.get("is_superadmin") == "1"
    st.session_state.admin_company_id = (
        int(cookies.get("admin_company_id")) if (cookies.get("admin_company_id") or "").isdigit() else None
    )
    # добавили идентификаторы пользователя
    st.session_state.user_id = int(cookies.get("user_id")) if (cookies.get("user_id") or "").isdigit() else None
    st.session_state.user_name = cookies.get("user_name") or "Гость"
    st.session_state.user_role = cookies.get("user_role") or None

# ——— Автовосстановление роли из БД, если авторизованы, а роль в сессии не определена
if st.session_state.get("auth") and not st.session_state.get("user_role"):
    # супер-админу сразу проставим роль
    if st.session_state.get("is_superadmin"):
        st.session_state.user_role = "Главный администратор"
    else:
        uid = st.session_state.get("user_id")
        if uid:
            db = SessionLocal()
            try:
                u = (
                    db.query(User)
                    .options(joinedload(User.position).joinedload(Position.role))
                    .get(uid)
                )
                st.session_state.user_role = (
                    u.position.role.name if u and u.position and u.position.role else "employee"
                )
                # подстрахуем cookies
                cookies["user_role"] = st.session_state.user_role or ""
                cookies.save()
            finally:
                db.close()


# =========================
#   АВТОРИЗАЦИЯ / РОУТИНГ
# =========================
if not st.session_state.auth:
    st.sidebar.title("Вход")
    login = st.sidebar.text_input("Логин")
    pwd = st.sidebar.text_input("Пароль", type="password")

    if st.sidebar.button("Войти"):
        # Супер‑админ из .env
        if login == SA_LOGIN and pwd == SA_PASS:
            st.session_state.auth = True
            st.session_state.is_superadmin = True
            st.session_state.is_company_admin = False
            st.session_state.admin_company_id = None
            st.session_state.user_id = 0
            st.session_state.user_name = "Жданов Андрей"
            st.session_state.user_role = "Главный администратор"

            cookies["auth"] = "1"
            cookies["is_superadmin"] = "1"
            cookies["is_company_admin"] = "0"
            cookies["admin_company_id"] = ""
            cookies["user_id"] = "0"
            cookies["user_name"] = st.session_state.user_name
            cookies["user_role"] = st.session_state.user_role
            cookies.save()
            st.rerun()
        else:
            # Обычный пользователь
            db = SessionLocal()
            try:
                user = (
                    db.query(User)
                    .options(joinedload(User.position).joinedload(Position.role))
                    .filter_by(login=login)
                    .first()
                )
                if user and user.hashed_password and bcrypt.checkpw(pwd.encode(), user.hashed_password.encode()):
                    role_name = user.position.role.name if (user.position and user.position.role) else "employee"
                    is_main_admin = role_name == "Главный администратор"

                    st.session_state.auth = True
                    st.session_state.is_superadmin = False
                    st.session_state.is_company_admin = is_main_admin
                    st.session_state.admin_company_id = user.company_id
                    st.session_state.user_id = user.id
                    st.session_state.user_name = user.name
                    st.session_state.user_role = role_name

                    cookies["auth"] = "1"
                    cookies["is_superadmin"] = "0"
                    cookies["is_company_admin"] = "1" if is_main_admin else "0"
                    cookies["admin_company_id"] = str(user.company_id or "")
                    cookies["user_id"] = str(user.id)
                    cookies["user_name"] = user.name or ""
                    cookies["user_role"] = role_name or ""
                    cookies.save()
                    st.rerun()
                else:
                    st.sidebar.error("Неверный логин или пароль")
            finally:
                db.close()
else:
    # Роутинг после авторизации (кнопка «Выйти» теперь рисуется в сайдбаре внутри панели)
    if st.session_state.is_superadmin:
        main_superadmin()
    else:
        company_admin_dashboard(st.session_state.admin_company_id)

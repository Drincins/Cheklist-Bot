import os
import streamlit as st
from dotenv import load_dotenv
from checklist.db.db import SessionLocal, init_db
from checklist.db.models import User, Company, Position, Role
from checklist.admcompany.main import company_admin_dashboard
from checklist.superadmintab import main_superadmin
import bcrypt
from sqlalchemy.orm import joinedload

# ——— cookies
from streamlit_cookies_manager import CookieManager, EncryptedCookieManager

# Настройка .env и БД
load_dotenv()
SA_LOGIN = os.getenv("SUPERADMIN_LOGIN")
SA_PASS = os.getenv("SUPERADMIN_PASSWORD")
init_db()

# ——— Настройка cookies (выбери свою секретную строку)
cookies = EncryptedCookieManager(
    prefix="checklist_", password="SECRET_COOKIE_PASSWORD_2024"
)
if not cookies.ready():
    st.stop()

# ——— Авторизация из cookies
if 'auth' not in st.session_state:
    st.session_state.auth = cookies.get('auth') == '1'
    st.session_state.is_company_admin = cookies.get('is_company_admin') == '1'
    st.session_state.is_superadmin = cookies.get('is_superadmin') == '1'
    st.session_state.admin_company_id = (
        int(cookies.get('admin_company_id')) if cookies.get('admin_company_id') and cookies.get('admin_company_id').isdigit() else None
    )

def logout_button():
    if st.button("🔒 Выйти"):
        st.session_state.auth = False
        st.session_state.is_company_admin = False
        st.session_state.is_superadmin = False
        st.session_state.admin_company_id = None
        # Очищаем cookies:
        cookies['auth'] = '0'
        cookies['is_superadmin'] = '0'
        cookies['is_company_admin'] = '0'
        cookies['admin_company_id'] = ''
        cookies.save()
        st.rerun()

# ——— Единая форма авторизации (с сохранением в cookies)
if not st.session_state.auth:
    st.sidebar.title("Вход")
    login = st.sidebar.text_input("Логин")
    pwd = st.sidebar.text_input("Пароль", type="password")
    if st.sidebar.button("Войти"):
        # Супер-админ (жёстко прописанный):
        if login == SA_LOGIN and pwd == SA_PASS:
            st.session_state.auth = True
            st.session_state.is_superadmin = True
            st.session_state.is_company_admin = False
            st.session_state.admin_company_id = None
            st.session_state.user_name = "Жданов Андрей"
            st.session_state.user_role = "Главный администратор"
            cookies['auth'] = '1'
            cookies['is_superadmin'] = '1'
            cookies['is_company_admin'] = '0'
            cookies['admin_company_id'] = ''
            cookies.save()
            st.rerun()
        else:
            db = SessionLocal()
            user = db.query(User).options(
                joinedload(User.position).joinedload(Position.role)
            ).filter_by(login=login).first()

            if user and bcrypt.checkpw(pwd.encode(), user.hashed_password.encode()):
                role_name = user.position.role.name if user.position and user.position.role else "Не указана"
                is_main_admin = (role_name == "Главный администратор")
                st.session_state.auth = True
                st.session_state.is_superadmin = False
                st.session_state.is_company_admin = is_main_admin
                st.session_state.admin_company_id = user.company_id
                st.session_state.user_name = user.name
                st.session_state.user_role = role_name
                cookies['auth'] = '1'
                cookies['is_superadmin'] = '0'
                cookies['is_company_admin'] = '1' if is_main_admin else '0'
                cookies['admin_company_id'] = str(user.company_id)
                cookies.save()
                st.rerun()
            else:
                st.sidebar.error("Неверный логин или пароль")

else:
    if st.session_state.is_superadmin:
        main_superadmin()
        logout_button()
    elif st.session_state.is_company_admin:
        company_admin_dashboard(st.session_state.admin_company_id)
        logout_button()

import os
import streamlit as st
from dotenv import load_dotenv
from checklist.db import SessionLocal, init_db
from checklist.models import User
from checklist.admcompany.main import company_admin_dashboard
from checklist.superadmintab import main_superadmin
import bcrypt

# ——— cookies
from streamlit_cookies_manager import EncryptedCookieManager

# Настройка .env и БД
load_dotenv()
SA_LOGIN = os.getenv("SUPERADMIN_LOGIN")
SA_PASS = os.getenv("SUPERADMIN_PASSWORD")
init_db()

# ——— Настройка cookies (выбери свою секретную строку)
cookies = EncryptedCookieManager(
    prefix="checklist_", password="SECRET_COOKIE_PASSWORD_2024"  # Поменяй пароль на свой!
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
        # Супер-админ:
        if login == SA_LOGIN and pwd == SA_PASS:
            st.session_state.auth = True
            st.session_state.is_superadmin = True
            st.session_state.is_company_admin = False
            st.session_state.admin_company_id = None
            # В cookies:
            cookies['auth'] = '1'
            cookies['is_superadmin'] = '1'
            cookies['is_company_admin'] = '0'
            cookies['admin_company_id'] = ''
            cookies.save()
            st.rerun()
        else:
            # Обычный админ компании:
            db = SessionLocal()
            user = db.query(User).filter_by(login=login, role="main_admin").first()
            db.close()
            if user and bcrypt.checkpw(pwd.encode(), user.hashed_password.encode()):
                st.session_state.auth = True
                st.session_state.is_superadmin = False
                st.session_state.is_company_admin = True
                st.session_state.admin_company_id = user.company_id
                # В cookies:
                cookies['auth'] = '1'
                cookies['is_superadmin'] = '0'
                cookies['is_company_admin'] = '1'
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

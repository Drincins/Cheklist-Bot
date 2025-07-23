import streamlit as st
import pandas as pd
from checklist.db import SessionLocal
from checklist.models import Company, User
from sqlalchemy.exc import IntegrityError
import bcrypt

def main_superadmin():
    db = SessionLocal()
    tabs = st.tabs(["Компании", "Добавить компанию", "Отчёты"])

    # — Вкладка 1 — Компании + просмотр пользователей
    with tabs[0]:
        st.subheader("Список компаний")
        companies = db.query(Company).all()
        selected = st.selectbox("Выберите компанию", [""] + [c.name for c in companies])
        if selected:
            comp = next(c for c in companies if c.name == selected)
            st.markdown(f"#### Пользователи компании «{comp.name}»")
            users = db.query(User).filter_by(company_id=comp.id).all()

            if users:
                df = pd.DataFrame([{
                    "ID": u.id,
                    "ФИО": u.name,
                    "Роль": u.role,
                    "Логин": u.login if u.login else "—",
                    "Телефон": u.phone if u.phone else "—",
                } for u in users])
                st.dataframe(df, use_container_width=True)
            else:
                st.info("Пользователей пока нет.")

    # — Вкладка 2 — Добавить компанию и админа
    with tabs[1]:
        st.subheader("Добавить компанию + админа")
        with st.form("new_company"):
            name = st.text_input("Название компании")
            login = st.text_input("Логин для админа")
            pwd = st.text_input("Пароль для админа", type="password")
            if st.form_submit_button("Создать"):
                if not (name and login and pwd):
                    st.error("Пожалуйста, заполните все поля")
                elif db.query(Company).filter_by(name=name).first():
                    st.error("Компания с таким именем уже существует")
                else:
                    try:
                        comp = Company(name=name)
                        db.add(comp)
                        db.commit()
                    except IntegrityError:
                        db.rollback()
                        st.error("Ошибка при создании компании")
                        return
                    hashed = bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode()
                    admin = User(
                        name="Main Admin",
                        phone="",
                        role="main_admin",
                        company_id=comp.id,
                        position_id=None,
                        login=login,
                        hashed_password=hashed
                    )
                    db.add(admin)
                    try:
                        db.commit()
                        st.success(f"Компания «{name}» и админ успешно созданы")
                    except IntegrityError:
                        db.rollback()
                        st.error("Логин занят — админ не создан")

    # — Вкладка 3 — Отчёты
    with tabs[2]:
        st.subheader("Отчёты (скоро...)")
        st.info("Здесь будут отчёты по компаниям")

    db.close()

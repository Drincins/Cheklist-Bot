import bcrypt
import streamlit as st
import pandas as pd
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from checklist.db.db import SessionLocal
from checklist.db.models import Company, User, Role, Position

MAIN_ROLE_NAME = "Главный администратор"
MAIN_POSITION_NAME = "Главный администратор"


def _ensure_main_role(db) -> Role:
    role = db.query(Role).filter(Role.name == MAIN_ROLE_NAME).first()
    if role:
        return role
    role = Role(name=MAIN_ROLE_NAME, level=100, description="Создано автоматически")
    db.add(role)
    try:
        db.commit()
        db.refresh(role)
    except IntegrityError:
        db.rollback()
        role = db.query(Role).filter(Role.name == MAIN_ROLE_NAME).first()
    if not role:
        raise RuntimeError("Не удалось создать роль главного администратора")
    return role


def _ensure_main_position(db, company_id: int, role: Role) -> Position:
    position = (
        db.query(Position)
        .filter(Position.company_id == company_id, Position.name == MAIN_POSITION_NAME)
        .first()
    )
    if position:
        return position
    position = Position(name=MAIN_POSITION_NAME, company_id=company_id, role_id=role.id)
    db.add(position)
    try:
        db.commit()
        db.refresh(position)
    except IntegrityError:
        db.rollback()
        position = (
            db.query(Position)
            .filter(Position.company_id == company_id, Position.name == MAIN_POSITION_NAME)
            .first()
        )
    if not position:
        raise RuntimeError("Не удалось создать позицию администратора")
    return position


def main_superadmin():
    db = SessionLocal()
    try:
        tabs = st.tabs([
            "Компании",
            "Добавить компанию",
            "Отладка",
        ])

        with tabs[0]:
            st.subheader("Список компаний")
            companies = db.query(Company).order_by(Company.name.asc()).all()
            options = [""] + [c.name for c in companies]
            selected = st.selectbox("Выберите компанию", options)
            if selected:
                company = next((c for c in companies if c.name == selected), None)
                if company:
                    st.markdown(f"#### Пользователи компании «{company.name}»")
                    users = (
                        db.query(User)
                        .options(joinedload(User.position).joinedload(Position.role))
                        .filter(User.company_id == company.id)
                        .order_by(User.name.asc())
                        .all()
                    )
                    if users:
                        rows = []
                        for u in users:
                            role_name = ""
                            if u.position and u.position.role:
                                role_name = u.position.role.name or ""
                            rows.append({
                                "ID": u.id,
                                "ФИО": u.name or "",
                                "Роль": role_name,
                                "Логин": u.login or "",
                                "Телефон": u.phone or "",
                            })
                        st.dataframe(pd.DataFrame(rows), use_container_width=True)
                    else:
                        st.info("В компании пока нет пользователей.")

        with tabs[1]:
            st.subheader("Добавление компании")
            with st.form("new_company_form"):
                name = st.text_input("Название компании")
                login = st.text_input("Логин главного админа")
                password = st.text_input("Пароль", type="password")
                submitted = st.form_submit_button("Создать")

            if submitted:
                if not (name and login and password):
                    st.error("Заполните название, логин и пароль.")
                    return
                if db.query(Company).filter(Company.name == name).first():
                    st.error("Компания с таким названием уже существует.")
                    return
                if db.query(User).filter(User.login == login).first():
                    st.error("Пользователь с таким логином уже существует.")
                    return

                comp = Company(name=name)
                db.add(comp)
                try:
                    db.commit()
                    db.refresh(comp)
                except IntegrityError:
                    db.rollback()
                    st.error("Не удалось создать компанию.")
                    return

                hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

                try:
                    role = _ensure_main_role(db)
                    position = _ensure_main_position(db, comp.id, role)
                except RuntimeError as exc:
                    st.error(str(exc))
                    return

                admin = User(
                    name="Main Admin",
                    phone="",
                    company_id=comp.id,
                    position_id=position.id,
                    login=login,
                    hashed_password=hashed,
                )
                db.add(admin)
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    st.error("Не удалось создать учётную запись администратора.")
                else:
                    st.success(f"Компания «{name}» успешно создана.")

        with tabs[2]:
            st.subheader("Отладка")
            st.info("Здесь можно размещать служебную информацию.")
    finally:
        db.close()

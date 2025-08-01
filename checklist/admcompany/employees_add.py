import streamlit as st
from checklist.db.db import SessionLocal
from checklist.db.models import User, Position, Department
from sqlalchemy.exc import IntegrityError

def employees_add(company_id):
    db = SessionLocal()
    st.subheader("Добавление нового сотрудника")

    # Подгружаем должности для выпадающего списка
    positions = db.query(Position).filter_by(company_id=company_id).all()
    if not positions:
        st.warning("Сначала добавьте хотя бы одну должность в разделе 'Должности'!")
        db.close()
        return
    position_options = {p.name: p.id for p in positions}

    # Подгружаем подразделения для выбора
    departments = db.query(Department).filter_by(company_id=company_id).all()
    if not departments:
        st.warning("Сначала добавьте хотя бы одно подразделение!")
        db.close()
        return
    dep_options = {d.name: d.id for d in departments}

    with st.form("add_user_form"):
        last_name = st.text_input("Фамилия")
        first_name = st.text_input("Имя")
        col1, col2 = st.columns([1, 5])
        with col1:
            st.markdown("### +7")
        with col2:
            raw_phone = st.text_input("Телефон (10 цифр)", max_chars=10)

        # Выбор должности
        pos_names = list(position_options.keys())
        selected_pos_name = st.selectbox("Должность", pos_names)
        position_id = position_options[selected_pos_name]

        # Выбор подразделения (single-select, если нужен multi — замени на multiselect)
        dep_names = list(dep_options.keys())
        selected_dep_name = st.selectbox("Подразделение", dep_names)
        department_id = dep_options[selected_dep_name]

        submitted = st.form_submit_button("Добавить")
        if submitted:
            if not (last_name and first_name and raw_phone):
                st.error("Пожалуйста, заполните все поля")
            elif not raw_phone.isdigit() or len(raw_phone) != 10:
                st.error("Телефон должен содержать ровно 10 цифр")
            else:
                phone = "+7" + raw_phone
                full_name = f"{last_name} {first_name}"
                existing = db.query(User).filter_by(phone=phone, company_id=company_id).first()
                if existing:
                    st.warning("Сотрудник с таким номером телефона уже существует.")
                else:
                    new_user = User(
                        name=full_name,
                        phone=phone,
                        login=None,
                        hashed_password=None,
                        company_id=company_id,
                        position_id=position_id
                    )
                    db.add(new_user)
                    db.commit()
                    # Привязываем к подразделению (many-to-many)
                    department = db.query(Department).get(department_id)
                    new_user.departments.append(department)
                    db.commit()
                    st.success(f"Сотрудник {full_name} успешно добавлен")
                    st.rerun()
    db.close()

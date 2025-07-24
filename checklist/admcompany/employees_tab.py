import streamlit as st
from checklist.db import SessionLocal
from checklist.models import User, Position
from sqlalchemy.exc import IntegrityError
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
import pandas as pd

def employees_tab(company_id):
    db = SessionLocal()
    st.subheader("Сотрудники и должности")

    sub_tabs = st.tabs(["Сотрудники", "Должности"])

    # ——— Вкладка 1: Сотрудники
    with sub_tabs[0]:
        st.subheader("Список сотрудников")
        users = db.query(User).filter_by(company_id=company_id, role="employee").all()
        positions = db.query(Position).filter_by(company_id=company_id).all()

        position_options = {p.name: p.id for p in positions}

        if users:
            # Готовим данные
            position_map = {p.id: p.name for p in positions}
            position_name_to_id = {v: k for k, v in position_map.items()}

            data = []
            for user in users:
                data.append({
                    "ID": user.id,
                    "ФИО": user.name,
                    "Телефон": user.phone or "",
                    "Подразделение": user.department or "",
                    "Должность": position_map.get(user.position_id, "Не указана")
                })

            df = pd.DataFrame(data)

            # Настройки таблицы
            gb = GridOptionsBuilder.from_dataframe(df)
            gb.configure_pagination()
            gb.configure_default_column(editable=True)
            gb.configure_column("ID", editable=False, hide=True)
            gb.configure_selection("multiple", use_checkbox=False)
            grid_options = gb.build()

            # Отображаем таблицу
            grid_response = AgGrid(
                df,
                gridOptions=grid_options,
                update_mode=GridUpdateMode.VALUE_CHANGED,
                allow_unsafe_jscode=True,
                theme="streamlit",
                height=500
            )

            edited_rows = grid_response["data"]

            if st.button("💾 Сохранить изменения"):
                try:
                    for row in edited_rows.to_dict(orient="records"):
                        user = db.query(User).get(row["ID"])
                        if user:
                            user.name = row["ФИО"]
                            user.phone = row["Телефон"]
                            user.department = row["Подразделение"]
                            user.position_id = position_name_to_id.get(row["Должность"], user.position_id)
                    db.commit()
                    st.success("Изменения сохранены")
                    st.rerun()
                except IntegrityError as e:
                    db.rollback()
                    st.error("Ошибка при сохранении")
                    st.exception(e)

        else:
            st.info("Сотрудников пока нет.")

    # ——— Вкладка 2: Должности
    with sub_tabs[1]:
        st.subheader("Должности компании")
        positions = db.query(Position).filter_by(company_id=company_id).all()

        if positions:
            for pos in positions:
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"– {pos.name}")
                with col2:
                    edit_btn = st.button("✏️ Редактировать", key=f"edit_pos_{pos.id}")

                if st.session_state.get(f"edit_mode_pos_{pos.id}", False) or edit_btn:
                    st.session_state[f"edit_mode_pos_{pos.id}"] = True
                    with st.expander(f"Редактирование — {pos.name}", expanded=True):
                        new_name = st.text_input("Название должности", value=pos.name, key=f"pos_name_{pos.id}")
                        col_save, col_cancel = st.columns(2)
                        with col_save:
                            if st.button("💾 Сохранить", key=f"save_pos_{pos.id}"):
                                pos.name = new_name
                                try:
                                    db.commit()
                                    st.success("Изменения сохранены")
                                    st.session_state[f"edit_mode_pos_{pos.id}"] = False
                                    st.rerun()
                                except IntegrityError as e:
                                    db.rollback()
                                    st.error("Ошибка при сохранении")
                                    st.exception(e)
                        with col_cancel:
                            if st.button("❌ Отмена", key=f"cancel_pos_{pos.id}"):
                                st.session_state[f"edit_mode_pos_{pos.id}"] = False
                                st.rerun()
        else:
            st.info("Пока нет ни одной должности.")

        st.markdown("---")
        st.subheader("Добавить новую должность")
        with st.form("add_position_form"):
            new_pos_name = st.text_input("Название должности")
            submit_pos = st.form_submit_button("Добавить")
            if submit_pos:
                if not new_pos_name:
                    st.error("Введите название должности")
                elif db.query(Position).filter_by(name=new_pos_name, company_id=company_id).first():
                    st.warning("Такая должность уже существует.")
                else:
                    db.add(Position(name=new_pos_name, company_id=company_id))
                    db.commit()
                    st.success("Должность добавлена")
                    st.rerun()

    db.close()

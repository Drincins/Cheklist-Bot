import streamlit as st
from checklist.db.db import SessionLocal
from checklist.db.models import User, Position, Role
from sqlalchemy.exc import IntegrityError
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

def employees_data_tab(company_id):
    db = SessionLocal()
    st.subheader("Список сотрудников")
    users = db.query(User).filter_by(company_id=company_id).all()
    positions = db.query(Position).filter_by(company_id=company_id).all()

    position_options = {p.name: p.id for p in positions}

    if users:
        # Готовим данные
        position_map = {p.id: p.name for p in positions}
        position_name_to_id = {v: k for k, v in position_map.items()}

        data = []
        for user in users:
            department_names = ", ".join([d.name for d in user.departments]) if user.departments else "—"
            data.append({
                "ID": user.id,
                "ФИО": user.name,
                "Телефон": user.phone or "",
                "Подразделение": department_names,
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

        if st.button("💾 Сохранить изменения", key="save_employees_data"):
            try:
                for row in edited_rows.to_dict(orient="records"):
                    user = db.query(User).get(row["ID"])
                    if user:
                        user.name = row["ФИО"]
                        user.phone = row["Телефон"]
                        # user.department = row["Подразделение"]  # <--- УБРАТЬ!
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

    db.close()

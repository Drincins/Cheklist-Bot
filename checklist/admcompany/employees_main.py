import streamlit as st

# Подтягиваем вкладку «Сотрудники»
from checklist.admcompany.employees_user import employees_user_tab

# Пытаемся подтянуть «Должности и доступы». Если файла пока нет — покажем заглушку.
try:
    from checklist.admcompany.employees_position import employees_position_tab
except Exception:
    def employees_position_tab(company_id: int):
        st.info("Вкладка «Должности и доступы» пока не реализована.")
        st.caption("Создай файл checklist/admcompany/employees_position.py с функцией employees_position_tab(company_id).")


def employees_main(company_id: int):
    st.subheader("👥 Сотрудники и доступы")

    tabs = st.tabs(["Сотрудники", "Должности и доступы"])
    with tabs[0]:
        employees_user_tab(company_id)
    with tabs[1]:
        employees_position_tab(company_id)

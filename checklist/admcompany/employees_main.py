import streamlit as st
from checklist.admcompany.employees_data import employees_data_tab
from checklist.admcompany.employees_add import employees_add
from checklist.db.models import User, Position, Role

def employees_main(company_id):
    st.subheader("👥 Сотрудники компании")
    tabs = st.tabs(["Список сотрудников", "Добавить сотрудника"])

    with tabs[0]:
        employees_data_tab(company_id)

    with tabs[1]:
        employees_add(company_id)

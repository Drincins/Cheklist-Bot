import streamlit as st
from checklist.admcompany.departments_data import departments_data_tab
from checklist.admcompany.departments_add import departments_add_tab

def departments_main(company_id):
    st.subheader("🏢 Подразделения компании")
    tabs = st.tabs(["Список подразделений", "Добавить подразделение"])

    with tabs[0]:
        departments_data_tab(company_id)

    with tabs[1]:
        departments_add_tab(company_id)

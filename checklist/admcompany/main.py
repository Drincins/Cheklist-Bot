import streamlit as st
from checklist.admcompany.employees_tab import employees_tab
from checklist.admcompany.add_employee_tab import add_employee_tab
from checklist.admcompany.checklists_tab import checklists_tab
from checklist.admcompany.add_checklist_tab import add_checklist_tab
from checklist.admcompany.reports_tab import reports_tab

def company_admin_dashboard(company_id):
    st.title("👨‍💼 Панель администратора компании")

    # Главное меню в сайдбаре
    menu = st.sidebar.radio(
        "Меню", 
        [
            "Сотрудники и должности",  # тут будет подтабы внутри
            "Добавить сотрудника",
            "Чек-листы",
            "Добавить чек-лист",
            "Отчёты"
        ],
        key="main_menu"
    )

    if menu == "Сотрудники и должности":
        employees_tab(company_id)
    elif menu == "Добавить сотрудника":
        add_employee_tab(company_id)
    elif menu == "Чек-листы":
        checklists_tab(company_id)
    elif menu == "Добавить чек-лист":
        add_checklist_tab(company_id)
    elif menu == "Отчёты":
        reports_tab(company_id)    
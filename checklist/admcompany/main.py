import streamlit as st
from checklist.admcompany.employees_main import employees_main
from checklist.admcompany.departments_main import departments_main
from checklist.admcompany.checklists_main import checklists_main
from checklist.admcompany.reports_tab import reports_tab

def company_admin_dashboard(company_id):
    st.title("👨‍💼 Панель администратора компании")
     # --- Блок информации о пользователе в сайдбаре ---
    with st.sidebar:
        st.markdown("#### 👤 Пользователь")
        user_name = st.session_state.get("user_name", "Гость")
        user_role = st.session_state.get("user_role", "Не определено")
        st.markdown(f"**{user_name}**")
        st.markdown(f"*Роль:* {user_role}")
        st.markdown("---")  # Разделитель перед меню

    # Главное меню в сайдбаре
    menu = st.sidebar.radio(
        "Меню", 
        [
            "Подразделения",
            "Сотрудники и должности",  # тут будет подтабы внутри
            "Чек-листы",
            "Отчёты"
        ],
        key="main_menu"
    )

    if menu == "Сотрудники и должности":
        employees_main(company_id)
    elif menu == "Чек-листы":
        checklists_main(company_id)
    elif menu == "Отчёты":
        reports_tab(company_id)    
    elif menu == "Подразделения":
        departments_main(company_id)    
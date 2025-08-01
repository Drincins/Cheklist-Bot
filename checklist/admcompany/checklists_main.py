import streamlit as st
from checklist.admcompany.checklists_data import checklists_data_tab
from checklist.admcompany.checklists_add import checklists_add_tab
from checklist.admcompany.checklists_edit import checklists_edit_tab

def checklists_main(company_id):
    st.subheader("📝 Чек-листы компании")
    tabs = st.tabs(["Все чек-листы", "Добавить чек-лист", "Редактировать чек-лист"])

    with tabs[0]:
        checklists_data_tab(company_id)
    with tabs[1]:
        checklists_add_tab(company_id)
    with tabs[2]:
        checklists_edit_tab(company_id)

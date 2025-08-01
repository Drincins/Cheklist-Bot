import streamlit as st
from checklist.db.db import SessionLocal
from checklist.db.models import Department
from sqlalchemy.exc import IntegrityError

def departments_add_tab(company_id):
    db = SessionLocal()
    st.markdown("### Добавить подразделение")
    with st.form("add_department_form"):
        dep_name = st.text_input("Название подразделения")
        submitted = st.form_submit_button("Добавить")
        if submitted:
            if not dep_name:
                st.error("Введите название подразделения")
            elif db.query(Department).filter_by(name=dep_name, company_id=company_id).first():
                st.warning("Такое подразделение уже есть в этой компании.")
            else:
                db.add(Department(name=dep_name, company_id=company_id))
                try:
                    db.commit()
                    st.success("Подразделение добавлено")
                    st.rerun()
                except IntegrityError as e:
                    db.rollback()
                    st.error("Ошибка при добавлении")
                    st.exception(e)
    db.close()

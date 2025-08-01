import streamlit as st
from checklist.db.db import SessionLocal
from checklist.db.models import Department

def departments_data_tab(company_id):
    db = SessionLocal()
    st.markdown("### Список подразделений")
    departments = db.query(Department).filter_by(company_id=company_id).all()
    if not departments:
        st.info("Пока нет ни одного подразделения.")
    else:
        for dep in departments:
            st.write(f"– {dep.name}")
            # можно добавить кнопки для редактирования/удаления
    db.close()

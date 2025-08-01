import streamlit as st
from checklist.db.db import SessionLocal
from checklist.db.models import Checklist, ChecklistQuestion

def checklists_data_tab(company_id):
    db = SessionLocal()
    st.markdown("### Все чек-листы компании")
    checklists = db.query(Checklist).filter_by(company_id=company_id).all()
    if not checklists:
        st.info("Чек-листов пока нет.")
    else:
        for cl in checklists:
            st.write(f"- {cl.name}")
    db.close()

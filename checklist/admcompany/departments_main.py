import streamlit as st
import pandas as pd
from typing import Optional, Iterable

from checklist.db.db import SessionLocal
from checklist.db.models import Department, User, Position, Checklist


# ---------- helpers ----------
def _dep_users(db, dep_id: int) -> list[User]:
    dep = db.query(Department).get(dep_id)
    if not dep:
        return []
    return list(dep.users or [])

def _dep_positions(db, dep_id: int) -> list[Position]:
    users = _dep_users(db, dep_id)
    pos_ids = {u.position_id for u in users if u.position_id}
    if not pos_ids:
        return []
    return db.query(Position).filter(Position.id.in_(pos_ids)).all()

def _union_checklists(positions: Iterable[Position]) -> list[Checklist]:
    seen = {}
    for p in positions:
        for cl in (p.checklists or []):
            seen[cl.id] = cl
    return list(seen.values())

def _create_or_update_department(db, company_id: int, dep_id: Optional[int], name: str) -> Department:
    name = (name or "").strip()
    if not name:
        raise ValueError("Название подразделения не может быть пустым")

    if dep_id:
        dep = db.query(Department).get(dep_id)
        if not dep:
            raise ValueError("Подразделение не найдено")
        dep.name = name
        db.commit()
        return dep

    # check duplicate in company
    exists = db.query(Department).filter(
        Department.company_id == company_id,
        Department.name == name
    ).first()
    if exists:
        raise ValueError("Такое подразделение уже существует в этой компании")

    dep = Department(company_id=company_id, name=name)
    db.add(dep)
    db.commit()
    db.refresh(dep)
    return dep


# ---------- modal wrapper (Streamlit >=1.31) ----------
def _modal(title: str):
    if hasattr(st, "dialog"):
        return st.dialog(title)
    # fallback: simple expander wrapper (визуально не модалка, но UX сохранится)
    def _cm(func):
        def _wrapped(*args, **kwargs):
            with st.expander(title, expanded=True):
                return func(*args, **kwargs)
        return _wrapped
    return _cm


# ---------- main tab ----------
def departments_main(company_id: int):
    st.subheader("🏢 Подразделения компании")

    db = SessionLocal()

    # --- таблица ---
    deps = (
        db.query(Department)
        .filter(Department.company_id == company_id)
        .order_by(Department.id.desc())
        .all()
    )

    if not deps:
        st.info("Пока нет ни одного подразделения.")
        df = pd.DataFrame(columns=["ID", "Подразделение", "Сотрудники", "Чек‑листы"])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        rows = []
        for d in deps:
            dep_positions = _dep_positions(db, d.id)
            cls_cnt = len(_union_checklists(dep_positions))
            rows.append({
                "ID": d.id,
                "Подразделение": d.name,
                "Сотрудники": len(d.users or []),
                "Чек‑листы": cls_cnt,
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # --- кнопка снизу: модальное окно «Добавить / Редактировать» ---
    if st.button("➕ Добавить / ✏️ Редактировать", type="primary"):
        _show_add_edit_modal(db, company_id)

    db.close()


# ---------- modal content ----------
def _show_add_edit_modal(db, company_id: int):
    @(_modal("Подразделение: добавить / редактировать"))
    def _content():
        mode = st.radio("Режим", ["Создать новое", "Редактировать существующее"], horizontal=True, key="dep_mode")

        dep_to_edit: Optional[Department] = None
        if mode == "Редактировать существующее":
            deps_all = (
                db.query(Department)
                .filter(Department.company_id == company_id)
                .order_by(Department.name.asc())
                .all()
            )
            options = {f"[{d.id}] {d.name}": d.id for d in deps_all}
            if not options:
                st.info("Нет подразделений для редактирования.")
                st.button("Закрыть", key="close_no_deps", on_click=st.rerun)
                return
            label = st.selectbox("Выберите подразделение", list(options.keys()))
            dep_to_edit = db.query(Department).get(options[label])

        default_name = dep_to_edit.name if dep_to_edit else ""
        new_name = st.text_input("Название подразделения", value=default_name, key="dep_name_input")

        c1, c2 = st.columns(2)
        with c1:
            if st.button("💾 Сохранить", type="primary", key="dep_save_btn"):
                try:
                    saved = _create_or_update_department(
                        db=db,
                        company_id=company_id,
                        dep_id=(dep_to_edit.id if dep_to_edit else None),
                        name=new_name,
                    )
                    st.success(f"Сохранено: [{saved.id}] {saved.name}")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
        with c2:
            st.button("Отмена", key="dep_cancel_btn", on_click=st.rerun)

    _content()

import streamlit as st
import pandas as pd
from typing import Optional
from checklist.db.db import SessionLocal
from checklist.db.models import Department


# ----------------------------
#   CRUD HELPERS
# ----------------------------
def _create_or_update_department(db, company_id: int, dep_id: Optional[int], name: str) -> Department:
    """Создать или обновить подразделение."""
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

    exists = (
        db.query(Department)
        .filter(Department.company_id == company_id, Department.name == name)
        .first()
    )
    if exists:
        raise ValueError("Такое подразделение уже существует в компании")

    dep = Department(company_id=company_id, name=name)
    db.add(dep)
    db.commit()
    db.refresh(dep)
    return dep


# ----------------------------
#   TAB ENTRY
# ----------------------------
def departments_main(company_id: int) -> None:
    """
    Вкладка «Подразделения»: таблица из БД + две кнопки снизу.
    Кнопки открывают маленькие поповеры (st.popover) с формами.
    """
    st.subheader("Подразделения компании")
    if company_id is None:
        st.info("Выберите компанию")
        return

    db = SessionLocal()
    try:
        deps = (
            db.query(Department)
            .filter(Department.company_id == company_id)
            .order_by(Department.name.asc())
            .all()
        )

        if not deps:
            st.info("Пока нет подразделений")
        else:
            rows = [{"Подразделение": d.name, "Сотрудников": len(d.users or [])} for d in deps]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.markdown("---")

        c1, c2 = st.columns(2)

        # --------- ПОПОВЕР ДОБАВЛЕНИЯ ---------
        with c1:
            with st.popover("➕ Добавить новое", use_container_width=True):
                st.markdown("**Новое подразделение**")
                name_add = st.text_input("Название", key="dep_add_name")
                btn_add = st.button("Сохранить", type="primary", key="dep_add_save")
                if btn_add:
                    try:
                        _create_or_update_department(db, company_id, None, name_add)
                        st.success("Подразделение добавлено")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))

        # --------- ПОПОВЕР РЕДАКТИРОВАНИЯ/УДАЛЕНИЯ ---------
        with c2:
            if deps:
                dep_map = {d.name: d.id for d in deps}
                selected_name = st.selectbox("Выберите подразделение", list(dep_map.keys()), key="dep_edit_select")

                with st.popover("✏️ Редактировать", use_container_width=True):
                    dep_id = dep_map[selected_name]
                    dep = db.query(Department).get(dep_id)

                    st.markdown(f"**Редактирование:** {dep.name}")
                    new_name = st.text_input("Название", value=dep.name, key="dep_edit_name")
                    cc1, cc2 = st.columns(2)
                    with cc1:
                        if st.button("Сохранить", type="primary", key="dep_edit_save"):
                            try:
                                _create_or_update_department(db, company_id, dep.id, new_name)
                                st.success("Сохранено")
                                st.rerun()
                            except Exception as exc:
                                st.error(str(exc))
                    with cc2:
                        # компактное подтверждение удаления внутри поповера
                        confirm = st.checkbox("Подтвердить удаление", key="dep_del_confirm")
                        if st.button("Удалить", type="secondary", key="dep_delete_btn", disabled=not confirm):
                            try:
                                dep.users.clear()   # отвязка, если есть связь
                                db.commit()
                                db.delete(dep)
                                db.commit()
                                st.success("Удалено")
                                st.rerun()
                            except Exception as exc:
                                db.rollback()
                                st.error(str(exc))
    finally:
        db.close()

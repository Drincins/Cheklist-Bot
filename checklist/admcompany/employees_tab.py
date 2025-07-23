import streamlit as st
from checklist.db import SessionLocal
from checklist.models import User, Position, Checklist 
from sqlalchemy.exc import IntegrityError

def employees_tab(company_id):
    db = SessionLocal()
    st.subheader("Сотрудники и должности")
    
    sub_tabs = st.tabs(["Сотрудники", "Должности"])
    
    with sub_tabs[0]:

        st.subheader("Список сотрудников")
        users = db.query(User).filter_by(company_id=company_id, role="employee").all()

        # Подгружаем справочник должностей для компании
        positions = db.query(Position).filter_by(company_id=company_id).all()
        # Если нет ни одной должности — подсказываем добавить
        if not positions:
            st.warning("Сначала добавьте должности в разделе справочников!")
            db.close()
            return
        position_options = {p.name: p.id for p in positions}

        if users:
            for user in users:
                col1, col2 = st.columns([3, 1])
                with col1:
                    # Находим название должности по id (или пишем "Не указана")
                    pos_name = next((p.name for p in positions if p.id == user.position_id), "Не указана")
                    st.write(f"👤 {user.name} ({user.phone}) — {pos_name}")
                with col2:
                    edit_btn = st.button("✏️ Редактировать", key=f"edit_{user.id}")

                if st.session_state.get(f"edit_mode_{user.id}", False) or edit_btn:
                    st.session_state[f"edit_mode_{user.id}"] = True
                    with st.expander(f"Редактирование — {user.name}", expanded=True):
                        new_name = st.text_input("ФИО", value=user.name, key=f"name_{user.id}")
                        new_phone = st.text_input("Телефон (+7...)", value=user.phone or "", key=f"phone_{user.id}")

                        # ВЫПАДАЮЩИЙ СПРАВОЧНИК ДОЛЖНОСТЕЙ
                        pos_names = list(position_options.keys())
                        pos_ids = list(position_options.values())
                        # Для корректного отображения текущей должности:
                        curr_idx = pos_ids.index(user.position_id) if user.position_id in pos_ids else 0
                        selected_pos_name = st.selectbox(
                            "Должность",
                            options=pos_names,
                            index=curr_idx,
                            key=f"pos_{user.id}"
                        )
                        position_id = position_options[selected_pos_name]

                        save = st.button("💾 Сохранить", key=f"save_{user.id}")
                        cancel = st.button("❌ Отмена", key=f"cancel_{user.id}")

                        if save:
                            user.name = new_name
                            user.phone = new_phone
                            user.position_id = position_id
                            try:
                                db.commit()
                                st.success("Изменения сохранены")
                                st.session_state[f"edit_mode_{user.id}"] = False
                                st.rerun()
                            except IntegrityError as e:
                                db.rollback()
                                st.error("Ошибка при обновлении")
                                st.exception(e)
                        if cancel:
                            st.session_state[f"edit_mode_{user.id}"] = False
                            st.rerun()
        else:
            st.info("Сотрудников пока нет.")
        # ——— Подвкладка 2 — Должности
    with sub_tabs[1]:
        st.markdown("### Должности компании")
        positions = db.query(Position).filter_by(company_id=company_id).all()
        checklists = db.query(Checklist).filter_by(company_id=company_id).all()

        if positions:
            for pos in positions:
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"– {pos.name}")
                with col2:
                    edit_btn = st.button("✏️ Редактировать", key=f"edit_pos_{pos.id}")

                # Редактирование должности + чек-листы
                if st.session_state.get(f"edit_mode_pos_{pos.id}", False) or edit_btn:
                    st.session_state[f"edit_mode_pos_{pos.id}"] = True
                    with st.expander(f"Редактирование — {pos.name}", expanded=True):
                        new_name = st.text_input("Название должности", value=pos.name, key=f"pos_name_{pos.id}")

                        # Список чек-листов (названия/id)
                        checklist_options = {cl.name: cl.id for cl in checklists}
                        selected_names = st.multiselect(
                            "Доступные чек-листы",
                            options=list(checklist_options.keys()),
                            default=[cl.name for cl in pos.checklists],
                            key=f"checklists_{pos.id}"
                        )
                        selected_ids = [checklist_options[name] for name in selected_names]

                        col_save, col_cancel = st.columns(2)
                        with col_save:
                            if st.button("💾 Сохранить", key=f"save_pos_{pos.id}"):
                                # Сохраняем имя
                                pos.name = new_name
                                # Привязка чек-листов
                                pos.checklists = [cl for cl in checklists if cl.id in selected_ids]
                                try:
                                    db.commit()
                                    st.success("Изменения сохранены")
                                    st.session_state[f"edit_mode_pos_{pos.id}"] = False
                                    st.rerun()
                                except IntegrityError as e:
                                    db.rollback()
                                    st.error("Ошибка при сохранении")
                                    st.exception(e)
                        with col_cancel:
                            if st.button("❌ Отмена", key=f"cancel_pos_{pos.id}"):
                                st.session_state[f"edit_mode_pos_{pos.id}"] = False
                                st.rerun()
        else:
            st.info("Пока нет ни одной должности.")

        st.markdown("---")
        st.subheader("Добавить новую должность")
        with st.form("add_position_form"):
            new_pos_name = st.text_input("Название должности")
            submit_pos = st.form_submit_button("Добавить")
            if submit_pos:
                if not new_pos_name:
                    st.error("Введите название должности")
                elif db.query(Position).filter_by(name=new_pos_name, company_id=company_id).first():
                    st.warning("Такая должность уже существует.")
                else:
                    db.add(Position(name=new_pos_name, company_id=company_id))
                    db.commit()
                    st.success("Должность добавлена")
                    st.rerun()
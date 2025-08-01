import streamlit as st
from checklist.db.db import SessionLocal
from checklist.db.models import Checklist, ChecklistQuestion, Position
from sqlalchemy.exc import IntegrityError

def checklists_edit_tab(company_id):
    db = SessionLocal()
    st.subheader("Редактировать чек-лист")
    # Загружаем все чек-листы компании
    checklists = db.query(Checklist).filter_by(company_id=company_id).all()
    if not checklists:
        st.info("В компании пока нет чек-листов.")
        db.close()
        return

    cl_names = [cl.name for cl in checklists]
    selected_name = st.selectbox("Выберите чек-лист для редактирования:", cl_names, key="edit_select")
    selected_cl = next(cl for cl in checklists if cl.name == selected_name)

    # --- Редактирование основных данных чек-листа ---
    with st.form("edit_checklist_form"):
        new_name = st.text_input("Название чек-листа", value=selected_cl.name)
        is_scored = st.checkbox("Оцениваемый чек-лист?", value=selected_cl.is_scored)
        save_cl = st.form_submit_button("💾 Сохранить изменения чек-листа")
        if save_cl:
            selected_cl.name = new_name
            selected_cl.is_scored = is_scored
            try:
                db.commit()
                st.success("Чек-лист обновлён")
                st.rerun()
            except IntegrityError as e:
                db.rollback()
                st.error("Ошибка при сохранении изменений")
                st.exception(e)

    st.markdown("### 🧑‍💼 Назначение чек-листа должностям")

    # --- Редактирование списка должностей ---
    all_positions = db.query(Position).filter_by(company_id=company_id).all()
    if all_positions:
        current_ids = [pos.id for pos in selected_cl.positions]
        pos_options = {p.name: p.id for p in all_positions}
        selected_names = st.multiselect(
            "Выберите должности, которым доступен этот чек-лист",
            options=list(pos_options.keys()),
            default=[p.name for p in all_positions if p.id in current_ids],
            key="edit_checklist_position_bind"
        )
        selected_ids = [pos_options[name] for name in selected_names]

        if st.button("💾 Сохранить назначения"):
            try:
                selected_cl.positions = [p for p in all_positions if p.id in selected_ids]
                db.commit()
                st.success("Привязка должностей сохранена.")
                st.rerun()
            except IntegrityError as e:
                db.rollback()
                st.error("Ошибка при сохранении назначений")
                st.exception(e)
    else:
        st.info("Нет доступных должностей в этой компании.")

    st.markdown("---")
    st.markdown("### Вопросы чек-листа")

    questions = db.query(ChecklistQuestion).filter_by(checklist_id=selected_cl.id).order_by(ChecklistQuestion.order).all()
    if questions:
        for q in questions:
            with st.expander(f"Вопрос {q.order}: {q.text}"):
                new_q_text = st.text_input("Текст вопроса", value=q.text, key=f"q_text_{q.id}")
                new_q_type = st.selectbox(
                    "Тип ответа", 
                    ["yesno", "scale", "short_text", "long_text"], 
                    index=["yesno", "scale", "short_text", "long_text"].index(q.type), 
                    key=f"q_type_{q.id}"
                )
                new_weight = st.number_input("Вес вопроса", value=int(q.meta['weight']) if q.meta and 'weight' in q.meta else 1, min_value=1, max_value=10, key=f"q_weight_{q.id}")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("💾 Сохранить вопрос", key=f"save_q_{q.id}"):
                        q.text = new_q_text
                        q.type = new_q_type
                        q.meta = {"weight": int(new_weight)}
                        try:
                            db.commit()
                            st.success("Вопрос обновлён")
                            st.rerun()
                        except IntegrityError as e:
                            db.rollback()
                            st.error("Ошибка при сохранении вопроса")
                            st.exception(e)
                with col2:
                    if st.button("🗑️ Удалить вопрос", key=f"del_q_{q.id}"):
                        db.delete(q)
                        db.commit()
                        st.success("Вопрос удалён")
                        st.rerun()
    else:
        st.info("В этом чек-листе пока нет вопросов.")

    # --- Добавить новый вопрос ---
    st.markdown("### Добавить новый вопрос")
    with st.form("add_new_q_form"):
        new_q_text = st.text_input("Текст нового вопроса")
        new_q_type = st.selectbox("Тип ответа", ["yesno", "scale", "short_text", "long_text"], key="add_type")
        new_weight = st.number_input("Вес вопроса", min_value=1, max_value=10, value=1, key="add_weight")
        add_new_q = st.form_submit_button("➕ Добавить вопрос")
        if add_new_q:
            order = (questions[-1].order + 1) if questions else 1
            db.add(ChecklistQuestion(
                checklist_id=selected_cl.id,
                order=order,
                text=new_q_text,
                type=new_q_type,
                required=True,
                meta={"weight": int(new_weight)}
            ))
            db.commit()
            st.success("Вопрос добавлен")
            st.rerun()

    db.close()

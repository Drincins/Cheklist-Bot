import streamlit as st
from checklist.db import SessionLocal
from checklist.models import Checklist, ChecklistQuestion
from sqlalchemy.exc import IntegrityError

def checklists_tab(company_id):
    db = SessionLocal()
    st.subheader("Чек-листы компании")

    tabs = st.tabs(["Просмотр чек-листов", "Редактировать чек-лист"])

    # --- Подвкладка 1: ПРОСМОТР
    with tabs[0]:
        checklists = db.query(Checklist).filter_by(company_id=company_id).all()
        if checklists:
            st.markdown("#### Все чек-листы:")
            for cl in checklists:
                st.write(f"- {cl.name}")
        else:
            st.info("Чек-листов пока нет.")
            db.close()
            return

        st.markdown("---")

        cl_names = [cl.name for cl in checklists]
        selected_name = st.selectbox("Выберите чек-лист для просмотра вопросов:", cl_names, key="view_select")
        selected_cl = next(cl for cl in checklists if cl.name == selected_name)

        questions = db.query(ChecklistQuestion).filter_by(checklist_id=selected_cl.id).order_by(ChecklistQuestion.order).all()
        st.markdown(f"#### Вопросы чек-листа: «{selected_cl.name}»")
        if questions:
            for q in questions:
                st.markdown(f"**{q.order}.** {q.text}  \n_Тип:_ {q.type}  " +
                    (f"_Вес:_ {q.meta.get('weight')}" if q.meta and 'weight' in q.meta else "")
                )
        else:
            st.info("У этого чек-листа пока нет вопросов.")

        st.markdown("---")
        if st.button(f"🗑️ Удалить чек-лист «{selected_cl.name}»", key="delete_view"):
            try:
                db.query(ChecklistQuestion).filter_by(checklist_id=selected_cl.id).delete()
                db.delete(selected_cl)
                db.commit()
                st.success("Чек-лист и все его вопросы удалены!")
                st.rerun()
            except IntegrityError as e:
                db.rollback()
                st.error("Ошибка при удалении чек-листа")
                st.exception(e)

    # --- Подвкладка 2: РЕДАКТИРОВАНИЕ
    with tabs[1]:
        checklists = db.query(Checklist).filter_by(company_id=company_id).all()
        if not checklists:
            st.info("Чек-листов пока нет.")
            db.close()
            return

        cl_names = [cl.name for cl in checklists]
        selected_name = st.selectbox("Выберите чек-лист для редактирования:", cl_names, key="edit_select")
        selected_cl = next(cl for cl in checklists if cl.name == selected_name)

        # Редактирование основных данных чек-листа
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

        # Добавить новый вопрос
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

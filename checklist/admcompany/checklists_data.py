import streamlit as st
from checklist.db.db import SessionLocal
from checklist.db.models import (
    Checklist,
    ChecklistQuestion,
    ChecklistAnswer,
    ChecklistQuestionAnswer,
)

def checklists_data_tab(company_id):
    db = SessionLocal()
    try:
        st.markdown("### Все чек-листы компании")

        # Стабильный порядок списка
        checklists = (
            db.query(Checklist)
            .filter_by(company_id=company_id)
            .order_by(Checklist.name.asc())
            .all()
        )

        if not checklists:
            st.info("Чек-листов пока нет.")
            return

        for cl in checklists:
            col1, col2 = st.columns([8, 2])
            with col1:
                st.write(f"• {cl.name}")
            with col2:
                if st.button("Удалить", key=f"del_cl_{cl.id}"):
                    # Запоминаем ID для подтверждения удаления
                    st.session_state["confirm_del_checklist_id"] = cl.id

        # Блок подтверждения удаления
        confirm_id = st.session_state.get("confirm_del_checklist_id")
        if confirm_id:
            cl = (
                db.query(Checklist)
                .filter_by(id=confirm_id, company_id=company_id)
                .first()
            )
            if cl:
                st.warning(f"Удалить чек-лист «{cl.name}» и все связанные данные (вопросы и ответы)?")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Да, удалить навсегда", key="confirm_del_yes"):
                        try:
                            # 1) Собираем id всех вопросов чек-листа
                            q_ids = [
                                qid for (qid,) in db.query(ChecklistQuestion.id)
                                .filter_by(checklist_id=cl.id)
                                .all()
                            ]

                            # 2) Удаляем ответы на вопросы (FK: checklist_question_answers.question_id → checklist_questions.id)
                            deleted_q_answers = 0
                            if q_ids:
                                deleted_q_answers = (
                                    db.query(ChecklistQuestionAnswer)
                                    .filter(ChecklistQuestionAnswer.question_id.in_(q_ids))
                                    .delete(synchronize_session=False)
                                )

                            # 3) Удаляем сами "ответы чек-листа" (FK: checklist_answers.checklist_id → checklists.id)
                            deleted_answers = (
                                db.query(ChecklistAnswer)
                                .filter_by(checklist_id=cl.id)
                                .delete(synchronize_session=False)
                            )

                            # 4) Удаляем вопросы чек-листа
                            deleted_questions = (
                                db.query(ChecklistQuestion)
                                .filter_by(checklist_id=cl.id)
                                .delete(synchronize_session=False)
                            )

                            # 5) Удаляем сам чек-лист
                            db.delete(cl)

                            # Фиксируем изменения
                            db.commit()

                            st.success(
                                f"Удалено: чек-лист «{cl.name}». "
                                f"Вопросов: {deleted_questions}, "
                                f"ответов на вопросы: {deleted_q_answers}, "
                                f"ответов по чек-листу: {deleted_answers}."
                            )
                        except Exception as e:
                            db.rollback()
                            st.error(f"Ошибка при удалении: {e}")
                        finally:
                            # Сбрасываем состояние и обновляем список
                            st.session_state.pop("confirm_del_checklist_id", None)
                            st.rerun()

                with c2:
                    if st.button("Отмена", key="confirm_del_no"):
                        st.session_state.pop("confirm_del_checklist_id", None)
                        st.info("Удаление отменено.")
            else:
                # Если чек-лист уже не найден — чистим состояние
                st.session_state.pop("confirm_del_checklist_id", None)
    finally:
        db.close()

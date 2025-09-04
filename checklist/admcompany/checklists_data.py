# checklist/admcompany/checklists_data.py
import streamlit as st
import pandas as pd
from sqlalchemy.orm import joinedload

from checklist.db.db import SessionLocal
from checklist.db.models import (
    Checklist,
    ChecklistQuestion,
    ChecklistAnswer,
    ChecklistQuestionAnswer,
    Position,  # для назначения должностей
)

# ---------------------------
#   ПОПОВЕР РЕДАКТИРОВАНИЯ
# ---------------------------
def _edit_checklist_popover(db, company_id: int, checklists: list[Checklist]):
    """
    Кнопка '✏️ Редактировать чек‑лист' с формой внутри st.popover:
      - выбор чек-листа,
      - изменение названия,
      - отметка 'оцениваемый',
      - привязка к должностям,
      - двухкликовое удаление (через session_state).
    """
    label = "✏️ Редактировать чек‑лист"
    if hasattr(st, "popover"):
        ctx = st.popover(label, use_container_width=True)
    else:
        # Фоллбэк на старые версии Streamlit
        ctx = st.expander(label, expanded=True)

    with ctx:
        if not checklists:
            st.info("Нет чек‑листов для редактирования.")
            return

        # Выбор чек-листа по имени
        by_name = {cl.name: cl for cl in checklists}
        selected_name = st.selectbox("Выберите чек‑лист", list(by_name.keys()), key="ck_pop_sel")
        cl = by_name[selected_name]

        # Пул должностей компании
        all_positions = (
            db.query(Position)
            .filter_by(company_id=company_id)
            .order_by(Position.name.asc())
            .all()
        )
        pos_map = {p.name: p.id for p in all_positions}
        current_ids = {p.id for p in (cl.positions or [])}
        default_names = [p.name for p in all_positions if p.id in current_ids]

        # Форма редактирования
        with st.form("ck_pop_form"):
            new_name = st.text_input("Название чек‑листа", value=cl.name, key="ck_pop_name")
            new_is_scored = st.checkbox("Оцениваемый чек‑лист?", value=cl.is_scored, key="ck_pop_scored")
            chosen_pos_names = st.multiselect(
                "Должности, которым назначен чек‑лист",
                options=list(pos_map.keys()),
                default=default_names,
                key="ck_pop_positions"
            )
            chosen_ids = [pos_map[n] for n in chosen_pos_names]

            col_save, col_del = st.columns(2)
            save_btn = col_save.form_submit_button("💾 Сохранить")
            del_btn  = col_del.form_submit_button("🗑️ Удалить", type="secondary")

        # Сохранение
        if save_btn:
            try:
                cl.name = (new_name or "").strip() or cl.name
                cl.is_scored = new_is_scored
                cl.positions = [p for p in all_positions if p.id in chosen_ids]
                db.commit()
                st.success("Изменения сохранены.")
                st.rerun()
            except Exception as e:
                db.rollback()
                st.error(f"Ошибка при сохранении: {e}")

        # Двухкликовое подтверждение удаления (через session_state)
        if del_btn:
            st.session_state["__del_ck_pending"] = cl.id

        if st.session_state.get("__del_ck_pending") == cl.id:
            st.warning("Удаление чек‑листа необратимо. Будут удалены все вопросы и ответы.")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("✅ Да, удалить навсегда", key=f"ck_confirm_del_{cl.id}"):
                    try:
                        # 1) собрать id вопросов
                        q_ids = [qid for (qid,) in db.query(ChecklistQuestion.id)
                                 .filter_by(checklist_id=cl.id).all()]
                        # 2) удалить ответы на вопросы
                        if q_ids:
                            db.query(ChecklistQuestionAnswer).filter(
                                ChecklistQuestionAnswer.question_id.in_(q_ids)
                            ).delete(synchronize_session=False)
                        # 3) удалить ответы чек‑листа
                        db.query(ChecklistAnswer).filter_by(
                            checklist_id=cl.id
                        ).delete(synchronize_session=False)
                        # 4) удалить вопросы
                        db.query(ChecklistQuestion).filter_by(
                            checklist_id=cl.id
                        ).delete(synchronize_session=False)
                        # 5) удалить сам чек‑лист
                        db.delete(cl)
                        db.commit()
                        st.success("Чек‑лист удалён.")
                    except Exception as e:
                        db.rollback()
                        st.error(f"Ошибка при удалении: {e}")
                    finally:
                        st.session_state.pop("__del_ck_pending", None)
                        st.rerun()
            with c2:
                if st.button("Отмена", key=f"ck_cancel_del_{cl.id}"):
                    st.session_state.pop("__del_ck_pending", None)
                    st.rerun()


# ---------------------------
#        TAB RENDER
# ---------------------------
def checklists_data_tab(company_id: int):
    db = SessionLocal()
    try:
        st.subheader("Все чек-листы компании")

        # Список чек‑листов с подгруженными должностями
        checklists = (
            db.query(Checklist)
            .options(joinedload(Checklist.positions))
            .filter(Checklist.company_id == company_id)
            .order_by(Checklist.name.asc())
            .all()
        )

        if not checklists:
            st.info("Чек‑листов пока нет.")
            return

        # «Красивая» таблица без ID
        rows = []
        for cl in checklists:
            pos_names = ", ".join(sorted([p.name for p in (cl.positions or [])])) or "—"
            rows.append({
                "Чек‑лист": cl.name,
                "Оцениваемый": "Да" if cl.is_scored else "Нет",
                "Должности (назначено)": pos_names,
            })
        st.markdown("### 📋 Существующие чек‑листы")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.markdown("---")

        # Кнопка-­поповер «Редактировать» в стиле employees_position
        c1, _ = st.columns([1, 3])
        with c1:
            _edit_checklist_popover(db, company_id, checklists)

        # ВНИМАНИЕ: отдельного блока подтверждения удаления НЕ нужно —
        # он уже реализован внутри popover через session_state["__del_ck_pending"].

    finally:
        db.close()

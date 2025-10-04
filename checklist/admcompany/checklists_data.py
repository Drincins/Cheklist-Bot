# -*- coding: utf-8 -*-
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
    Position,
)


# ---------------------------
#   Редактирование чек-листа
# ---------------------------
def _edit_checklist_popover(db, company_id: int, checklists: list[Checklist]):
    label = "Редактировать/Удалить чек-лист"
    ctx = st.popover(label, use_container_width=True) if hasattr(st, "popover") else st.expander(label, expanded=False)

    with ctx:
        if not checklists:
            st.info("Чек-листов пока нет.")
            return

        # Выбор чек-листа по названию
        by_name = {cl.name: cl for cl in checklists}
        selected_name = st.selectbox("Выберите чек-лист", list(by_name.keys()), key="ck_pop_sel")
        cl = by_name[selected_name]

        # Все позиции компании
        all_positions = (
            db.query(Position)
            .filter_by(company_id=company_id)
            .order_by(Position.name.asc())
            .all()
        )
        pos_map = {p.name: p.id for p in all_positions}
        current_ids = {p.id for p in (cl.positions or [])}
        default_names = [p.name for p in all_positions if p.id in current_ids]

        with st.form("ck_pop_form"):
            new_name = st.text_input("Название чек-листа", value=cl.name, key="ck_pop_name")
            new_is_scored = st.checkbox("Оценочный чек-лист?", value=cl.is_scored, key="ck_pop_scored")
            chosen_pos_names = st.multiselect(
                "Доступен для должностей",
                options=list(pos_map.keys()),
                default=default_names,
                key="ck_pop_positions",
            )
            chosen_ids = [pos_map[n] for n in chosen_pos_names]

            col_save, col_del = st.columns(2)
            save_btn = col_save.form_submit_button("Сохранить изменения")
            del_btn = col_del.form_submit_button("Удалить чек-лист", type="secondary")

        if save_btn:
            try:
                cl.name = (new_name or "").strip() or cl.name
                cl.is_scored = new_is_scored
                cl.positions = [p for p in all_positions if p.id in chosen_ids]
                db.commit()
                st.success("Сохранено.")
                st.rerun()
            except Exception as e:
                db.rollback()
                st.error(f"Ошибка при сохранении: {e}")

        # Подтверждение удаления через session_state
        if del_btn:
            st.session_state["__del_ck_pending"] = cl.id

        if st.session_state.get("__del_ck_pending") == cl.id:
            st.warning("Подтверждаете удаление чек-листа? Действие необратимо.")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Да, удалить", key=f"ck_confirm_del_{cl.id}"):
                    try:
                        # 1) Все вопросы этого чек-листа
                        q_ids = [qid for (qid,) in db.query(ChecklistQuestion.id).filter_by(checklist_id=cl.id).all()]
                        # 2) Удаляем ответы на вопросы
                        if q_ids:
                            db.query(ChecklistQuestionAnswer).filter(
                                ChecklistQuestionAnswer.question_id.in_(q_ids)
                            ).delete(synchronize_session=False)
                        # 3) Удаляем ответы по чек-листу
                        db.query(ChecklistAnswer).filter_by(checklist_id=cl.id).delete(synchronize_session=False)
                        # 4) Удаляем вопросы
                        db.query(ChecklistQuestion).filter_by(checklist_id=cl.id).delete(synchronize_session=False)
                        # 5) Удаляем сам чек-лист
                        db.delete(cl)
                        db.commit()
                        st.success("Чек-лист удалён.")
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
        st.subheader("Список чек-листов компании")

        # Полноэкранное добавление (не через popover)
        if st.session_state.get("__add_ck_full"):
            from .checklists_add import checklists_add_tab
            if st.button("Назад к списку чек-листов", key="add_full_back"):
                st.session_state["__add_ck_full"] = False
                st.rerun()
            checklists_add_tab(company_id, embedded=False)
            return

        # Список чек-листов c позициями
        checklists = (
            db.query(Checklist)
            .options(joinedload(Checklist.positions))
            .filter(Checklist.company_id == company_id)
            .order_by(Checklist.name.asc())
            .all()
        )

        # Отобразим таблицу или пустое состояние
        if not checklists:
            st.info("Чек-листов пока нет.")
        else:
            rows = []
            for cl in checklists:
                pos_names = ", ".join(sorted([p.name for p in (cl.positions or [])])) or "—"
                rows.append({
                    "Чек-лист": cl.name,
                    "Оценочный": "Да" if cl.is_scored else "Нет",
                    "Доступен должностям": pos_names,
                })
            st.markdown("### Доступные чек-листы")
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.markdown("---")

        # Управление: редактирование и создание нового чек-листа
        c1, c2 = st.columns([1, 1])
        with c1:
            _edit_checklist_popover(db, company_id, checklists)
        with c2:
            if st.button("Новый чек-лист", key="add_ck_full_btn"):
                st.session_state["__add_ck_full"] = True
                st.rerun()

    finally:
        db.close()


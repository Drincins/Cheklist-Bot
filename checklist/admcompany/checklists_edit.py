# -*- coding: utf-8 -*-
# checklist/admcompany/checklists_edit.py

import streamlit as st
import pandas as pd
from typing import Optional, List, Dict, Any

from checklist.db.db import SessionLocal
from checklist.db.models import (
    Checklist,
    ChecklistSection,
    ChecklistQuestion,
)


QUESTION_TYPES = [
    ("yesno", "Да/Нет"),
    ("scale", "Шкала (1-10)"),
    ("short_text", "Короткий текст"),
    ("long_text", "Длинный текст"),
]


# ----------------------------
#   HELPERS
# ----------------------------
def _load_checklist(db, checklist_id: int) -> Optional[Checklist]:
    return db.query(Checklist).get(checklist_id)


def _get_sections(db, checklist_id: int) -> List[ChecklistSection]:
    return (
        db.query(ChecklistSection)
        .filter(ChecklistSection.checklist_id == checklist_id)
        .order_by(ChecklistSection.order.asc())
        .all()
    )


def _get_section_questions(db, section_id: int) -> List[ChecklistQuestion]:
    return (
        db.query(ChecklistQuestion)
        .filter(ChecklistQuestion.section_id == section_id)
        .order_by(ChecklistQuestion.order.asc())
        .all()
    )


def _next_order_for_section(db, section_id: int) -> int:
    last = (
        db.query(ChecklistQuestion.order)
        .filter(ChecklistQuestion.section_id == section_id)
        .order_by(ChecklistQuestion.order.desc())
        .first()
    )
    return (last[0] + 1) if last else 1


def _next_order_for_sections(db, checklist_id: int) -> int:
    last = (
        db.query(ChecklistSection.order)
        .filter(ChecklistSection.checklist_id == checklist_id)
        .order_by(ChecklistSection.order.desc())
        .first()
    )
    return (last[0] + 1) if last else 1


def _reorder_sections_to(db, checklist_id: int, section_id: int, new_order: int):
    sections = (
        db.query(ChecklistSection)
        .filter(ChecklistSection.checklist_id == checklist_id)
        .order_by(ChecklistSection.order.asc())
        .all()
    )
    if not sections:
        return
    target = next((s for s in sections if s.id == section_id), None)
    if not target:
        return
    others = [s for s in sections if s.id != section_id]
    pos = max(1, min(new_order, len(others) + 1))
    others.insert(pos - 1, target)
    for idx, s in enumerate(others, 1):
        s.order = idx
    db.commit()


def _reorder_question_to(db, q: ChecklistQuestion, target_section_id: int, new_order: int):
    # Compress orders in old section if moving
    if q.section_id != target_section_id:
        old = (
            db.query(ChecklistQuestion)
            .filter(ChecklistQuestion.section_id == q.section_id)
            .order_by(ChecklistQuestion.order.asc())
            .all()
        )
        old = [i for i in old if i.id != q.id]
        for idx, i in enumerate(old, 1):
            i.order = idx

    items = (
        db.query(ChecklistQuestion)
        .filter(ChecklistQuestion.section_id == target_section_id)
        .order_by(ChecklistQuestion.order.asc())
        .all()
    )
    if q.section_id == target_section_id:
        items = [i for i in items if i.id != q.id]
    pos = max(1, min(new_order, len(items) + 1))
    q.section_id = target_section_id
    items.insert(pos - 1, q)
    for idx, i in enumerate(items, 1):
        i.order = idx
    db.commit()


# ----------------------------
#   SECTIONS CRUD (popovers)
# ----------------------------
def _add_section_popover(db, checklist_id: int):
    with st.popover("Добавить раздел", use_container_width=True):
        st.markdown("**Новый раздел**")
        title = st.text_input("Название раздела", key="sec_add_title")
        desc = st.text_area("Описание (опционально)", key="sec_add_desc")
        is_req = st.checkbox("Обязательный раздел", value=False, key="sec_add_required")
        if st.button("Сохранить раздел", type="primary", key="sec_add_save"):
            try:
                sec = ChecklistSection(
                    checklist_id=checklist_id,
                    title=(title or "").strip(),
                    description=(desc or "").strip() or None,
                    order=_next_order_for_sections(db, checklist_id),
                    is_required=bool(is_req),
                )
                if not sec.title:
                    raise ValueError("Введите название раздела")
                db.add(sec)
                db.commit()
                st.success("Раздел добавлен")
                st.rerun()
            except Exception as exc:
                db.rollback()
                st.error(str(exc))


def _edit_section_dialog(db, checklist_id: int):
    with st.popover("Изменить раздел", use_container_width=True):
        sections = _get_sections(db, checklist_id)
        if not sections:
            st.info("Сначала добавьте хотя бы один раздел.")
            return
        sel = st.selectbox(
            "Раздел",
            options=[f"{s.order}. {s.title}" for s in sections],
            key="sec_edit_pick_in_popover",
        )
        ord_ = int(sel.split(".", 1)[0])
        sec = next(s for s in sections if s.order == ord_)

        st.markdown("**Редактирование раздела**")
        title = st.text_input("Название раздела", value=sec.title, key=f"sec_ed_title_{sec.id}")
        desc = st.text_area("Описание", value=sec.description or "", key=f"sec_ed_desc_{sec.id}")
        is_req = st.checkbox("Обязательный раздел", value=bool(sec.is_required), key=f"sec_ed_required_{sec.id}")

        max_order = len(sections)
        new_order = st.number_input(
            "Порядок",
            min_value=1,
            max_value=max_order,
            value=int(sec.order),
            key=f"sec_ed_order_{sec.id}",
        )

        c1, c4 = st.columns([1, 1])
        with c1:
            if st.button("Сохранить", type="primary", key=f"sec_ed_save_{sec.id}"):
                try:
                    sec.title = (title or "").strip()
                    sec.description = (desc or "").strip() or None
                    sec.is_required = bool(is_req)
                    if not sec.title:
                        raise ValueError("Введите название раздела")
                    db.commit()
                    if int(new_order) != sec.order:
                        _reorder_sections_to(db, sec.checklist_id, sec.id, int(new_order))
                    st.success("Сохранено")
                    st.rerun()
                except Exception as exc:
                    db.rollback()
                    st.error(str(exc))
        with c4:
            confirm = st.checkbox("Подтвердить удаление", key=f"sec_del_confirm_{sec.id}")
            if st.button("Удалить", type="secondary", disabled=not confirm, key=f"sec_del_{sec.id}"):
                try:
                    first = (
                        db.query(ChecklistSection)
                        .filter(ChecklistSection.checklist_id == sec.checklist_id, ChecklistSection.id != sec.id)
                        .order_by(ChecklistSection.order.asc())
                        .first()
                    )
                    if first:
                        db.query(ChecklistQuestion).filter(ChecklistQuestion.section_id == sec.id).update(
                            {ChecklistQuestion.section_id: first.id}
                        )
                    db.delete(sec)
                    db.commit()
                    st.success("Удалено")
                    st.rerun()
                except Exception as exc:
                    db.rollback()
                    st.error(str(exc))


# ----------------------------
#   QUESTIONS (popovers)
# ----------------------------
def _add_question_popover(db, section: ChecklistSection, is_scored: bool):
    with st.popover("Добавить вопрос", use_container_width=True):
        answer_types = ["Короткий текст", "Длинный текст", "Да/Нет", "Шкала (1-10)"]
        if is_scored:
            answer_types = ["Да/Нет", "Шкала (1-10)"]
        with st.form(f"add_question_form_{section.id}", clear_on_submit=True):
            q_text = st.text_input("Текст вопроса", key=f"q_text_{section.id}")
            q_type = st.selectbox("Тип ответа", options=answer_types, key=f"q_type_{section.id}")
            q_weight = None
            if is_scored and q_type in ("Да/Нет", "Шкала (1-10)"):
                q_weight = st.number_input("Вес (1-10)", min_value=1, max_value=10, value=1, key=f"q_weight_{section.id}")
            req_photo = st.checkbox("Требовать фото", value=False, key=f"q_req_photo_{section.id}")
            req_comment = st.checkbox("Требовать комментарий", value=False, key=f"q_req_comment_{section.id}")
            q_required = st.checkbox("Обязательный вопрос?", value=True, key=f"q_required_{section.id}")
            submit = st.form_submit_button("Добавить")
        if submit:
            try:
                txt = (q_text or "").strip()
                if not txt:
                    st.warning("Введите текст вопроса")
                    return
                type_map = {
                    "Да/Нет": "yesno",
                    "Шкала (1-10)": "scale",
                    "Короткий текст": "short_text",
                    "Длинный текст": "long_text",
                }
                meta = {"min": 1, "max": 10} if q_type == "Шкала (1-10)" else None
                db.add(
                    ChecklistQuestion(
                        checklist_id=section.checklist_id,
                        section_id=section.id,
                        order=_next_order_for_section(db, section.id),
                        text=txt,
                        type=type_map[q_type],
                        required=bool(q_required),
                        weight=(int(q_weight) if q_weight is not None else None),
                        require_photo=bool(req_photo),
                        require_comment=bool(req_comment),
                        meta=meta,
                    )
                )
                db.commit()
                st.success("Вопрос добавлен")
                st.rerun()
            except Exception as exc:
                db.rollback()
                st.error(str(exc))


def _edit_question_popover(db, section: ChecklistSection, sections_for_move: List[ChecklistSection]):
    with st.popover("Редактировать вопрос", use_container_width=True):
        qs = _get_section_questions(db, section.id)
        if not qs:
            st.info("В этом разделе пока нет вопросов.")
            return
        q_sel = st.selectbox(
            "Вопрос",
            options=[f"{q.order}. {q.text[:40]}{'...' if len(q.text)>40 else ''}" for q in qs],
            key=f"q_pick_{section.id}",
        )
        q_ord = int(q_sel.split(".", 1)[0])
        q = next(q for q in qs if q.order == q_ord)

        st.markdown("**Редактирование вопроса**")
        text_val = st.text_area("Текст вопроса", value=q.text, key=f"q_ed_text_{q.id}")

        qtype_label = next(lbl for k, lbl in QUESTION_TYPES if k == q.type)
        qtype_new_label = st.selectbox(
            "Тип ответа",
            options=[lbl for _, lbl in QUESTION_TYPES],
            index=[lbl for _, lbl in QUESTION_TYPES].index(qtype_label),
            key=f"q_ed_type_lbl_{q.id}",
        )
        type_key = next(k for k, lbl in QUESTION_TYPES if lbl == qtype_new_label)

        required = st.checkbox("Обязательный", value=bool(q.required), key=f"q_ed_req_{q.id}")
        require_photo = st.checkbox("Требовать фото", value=bool(q.require_photo), key=f"q_ed_photo_{q.id}")
        require_comment = st.checkbox("Требовать комментарий", value=bool(q.require_comment), key=f"q_ed_comm_{q.id}")

        meta: Dict[str, Any] = {}
        if type_key == "scale":
            cur_min = (q.meta or {}).get("min", 1)
            cur_max = (q.meta or {}).get("max", 10)
            c1, c2 = st.columns(2)
            with c1:
                meta_min = st.number_input("Мин", value=int(cur_min), step=1, key=f"q_ed_meta_min_{q.id}")
            with c2:
                meta_max = st.number_input("Макс", value=int(cur_max), step=1, key=f"q_ed_meta_max_{q.id}")
            if meta_max < meta_min:
                st.warning("Макс не может быть меньше Мин.")
            meta = {"min": int(meta_min), "max": int(meta_max)}

        move_to_title = st.selectbox(
            "Раздел",
            options=[s.title for s in sections_for_move],
            index=[s.id for s in sections_for_move].index(q.section_id) if q.section_id else 0,
            key=f"q_ed_move_to_{q.id}",
        )
        move_to_id = next(s.id for s in sections_for_move if s.title == move_to_title)

        # Порядок в целевом разделе
        target_count = (
            db.query(ChecklistQuestion)
            .filter(ChecklistQuestion.section_id == move_to_id)
            .count()
        )
        max_order = target_count if move_to_id == q.section_id else (target_count + 1)
        default_order = q.order if move_to_id == q.section_id else (target_count + 1)
        new_order = st.number_input(
            "Порядок",
            min_value=1,
            max_value=max(1, int(max_order)),
            value=int(default_order),
            key=f"q_ed_order_{q.id}",
        )

        c1, c4 = st.columns([1, 1])
        with c1:
            if st.button("Сохранить", type="primary", key=f"q_ed_save_{q.id}"):
                try:
                    q.text = (text_val or "").strip()
                    q.type = type_key
                    q.required = bool(required)
                    q.require_photo = bool(require_photo)
                    q.require_comment = bool(require_comment)
                    q.meta = meta or None
                    if not q.text:
                        raise ValueError("Введите текст вопроса")
                    db.commit()
                    _reorder_question_to(db, q, move_to_id, int(new_order))
                    st.success("Сохранено")
                    st.rerun()
                except Exception as exc:
                    db.rollback()
                    st.error(str(exc))
        with c4:
            confirm = st.checkbox("Подтвердить удаление", key=f"q_del_confirm_{q.id}")
            if st.button("Удалить", type="secondary", disabled=not confirm, key=f"q_del_{q.id}"):
                try:
                    db.delete(q)
                    db.commit()
                    st.success("Удалено")
                    st.rerun()
                except Exception as exc:
                    db.rollback()
                    st.error(str(exc))


# ----------------------------
#   ENTRY (selected checklist)
# ----------------------------
def checklists_edit(checklist_id: int):
    db = SessionLocal()
    try:
        ck = _load_checklist(db, checklist_id)
        if not ck:
            st.error("Чек-лист не найден")
            return

        st.markdown(f"**Чек-лист:** {ck.name}")
        st.caption(f"ID: {ck.id} • Оценочный: {'Да' if ck.is_scored else 'Нет'}")
        tabs = st.tabs(["Разделы", "Вопросы"])

        # -------- Разделы --------
        with tabs[0]:
            sections = _get_sections(db, ck.id)
            if not sections:
                st.info("Разделов пока нет. Добавьте раздел ниже.")
            else:
                rows = [
                    {"Порядок": s.order, "Название": s.title, "Обязательный": "Да" if s.is_required else "Нет"}
                    for s in sections
                ]
                st.dataframe(pd.DataFrame(rows).sort_values(by="Порядок"), use_container_width=True, hide_index=True)

            c1, c2 = st.columns(2)
            with c1:
                if sections:
                    _edit_section_dialog(db, ck.id)
            with c2:
                _add_section_popover(db, ck.id)

        # -------- Вопросы --------
        with tabs[1]:
            sections = _get_sections(db, ck.id)
            if not sections:
                st.info("Сначала добавьте хотя бы один раздел.")
                return

            chosen = st.selectbox(
                "Раздел",
                options=[f"{s.order}. {s.title}" for s in sections],
                key="q_section_select",
            )
            ord_ = int(chosen.split(".", 1)[0])
            active_sec = next(s for s in sections if s.order == ord_)

            qs = _get_section_questions(db, active_sec.id)
            if qs:
                q_rows = [
                    {
                        "Порядок": q.order,
                        "Текст": q.text,
                        "Тип": next(lbl for k, lbl in QUESTION_TYPES if k == q.type),
                        "Обязательный": "Да" if q.required else "Нет",
                        "Фото": "Да" if q.require_photo else "Нет",
                        "Комментарий": "Да" if q.require_comment else "Нет",
                    }
                    for q in qs
                ]
                st.dataframe(pd.DataFrame(q_rows).sort_values(by="Порядок"), use_container_width=True, hide_index=True)
            else:
                st.info("Вопросов пока нет. Добавьте вопрос ниже.")

            cqa1, cqa2 = st.columns(2)
            with cqa1:
                _add_question_popover(db, active_sec, bool(ck.is_scored))
            with cqa2:
                if qs:
                    _edit_question_popover(db, active_sec, sections)

    finally:
        db.close()


# ----------------------------
#   TAB WRAPPER (select checklist)
# ----------------------------
def checklists_edit_tab(company_id: int):
    db = SessionLocal()
    try:
        checklists = (
            db.query(Checklist)
            .filter(Checklist.company_id == company_id)
            .order_by(Checklist.name.asc())
            .all()
        )

        if not checklists:
            st.info("Чек-листов пока нет.")
            return

        selected = st.selectbox(
            "Выберите чек-лист для редактирования",
            options=checklists,
            format_func=lambda c: getattr(c, "name", str(c)),
            key="ck_edit_tab_select",
        )

        if selected:
            checklists_edit(selected.id)
    finally:
        db.close()


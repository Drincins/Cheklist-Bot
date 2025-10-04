# -*- coding: utf-8 -*-
# checklist/admcompany/checklists_add.py

"""
Чистый мастер добавления нового чек-листа (без редактирования существующих).

Шаг 1: название, тип (оценочный/нет), должности.
Шаг 2: последовательное создание разделов и добавление вопросов в активный раздел;
       затем кнопка «Новый раздел» и вопросы к нему.
"""

import streamlit as st
from typing import Optional, Dict, List
from sqlalchemy.exc import IntegrityError

from checklist.db.db import SessionLocal
from checklist.db.models import Checklist, ChecklistQuestion, ChecklistSection, Position


def checklists_add_tab(company_id: int, embedded: bool = False, dialog_state_key: Optional[str] = None):
    db = SessionLocal()
    try:
        if not embedded:
            st.subheader("Добавить чек-лист")

        ss = st.session_state
        if "cl_add_step" not in ss:
            ss.cl_add_step = 1
        if "cl_add_form" not in ss:
            ss.cl_add_form = {
                "name": "",
                "is_scored": False,
                "positions": [],  # [position_id]
                # sections: list of {title, description, is_required, questions:[{...}]}
                "sections": [],
            }
        if "active_section_idx" not in ss:
            ss.active_section_idx = 0

        def _ensure_first_section():
            if not ss.cl_add_form["sections"]:
                ss.cl_add_form["sections"].append({
                    "title": "Раздел 1",
                    "description": "",
                    "is_required": False,
                    "questions": [],
                })
                ss.active_section_idx = 0

        # Встроенный режим: кнопка закрыть
        if embedded:
            if st.button("Закрыть", key="cl_add_close"):
                if dialog_state_key:
                    ss[dialog_state_key] = False
                st.rerun()

        # =============================================
        # Шаг 1 — основные поля чек-листа
        # =============================================
        if ss.cl_add_step == 1:
            with st.form("create_checklist_form", clear_on_submit=False):
                name = st.text_input("Название чек-листа", value=ss.cl_add_form.get("name", ""))
                is_scored = st.checkbox("Оценочный чек-лист?", value=ss.cl_add_form.get("is_scored", False))

                all_positions = (
                    db.query(Position)
                    .filter_by(company_id=company_id)
                    .order_by(Position.name.asc())
                    .all()
                )
                pos_map: Dict[str, int] = {p.name: p.id for p in all_positions}
                default_names = [p.name for p in all_positions if p.id in ss.cl_add_form.get("positions", [])]
                chosen_pos_names = st.multiselect(
                    "Должности (множественный выбор)",
                    options=list(pos_map.keys()),
                    default=default_names,
                    key="add_step1_pos_multiselect",
                )
                submit = st.form_submit_button("Далее")

            if submit:
                nm = (name or "").strip()
                if not nm:
                    st.error("Введите название чек-листа")
                else:
                    ss.cl_add_form["name"] = nm
                    ss.cl_add_form["is_scored"] = bool(is_scored)
                    ss.cl_add_form["positions"] = [pos_map[n] for n in chosen_pos_names]
                    ss.cl_add_step = 2
                    st.rerun()

        # =============================================
        # Шаг 2 — последовательные разделы и вопросы
        # =============================================
        if ss.cl_add_step == 2:
            st.markdown(f"**Чек-лист:** {ss.cl_add_form['name']}")
            st.caption("Тип: " + ("Оценочный" if ss.cl_add_form.get("is_scored") else "Без оценки"))

            # Выбранные должности (если есть)
            if ss.cl_add_form.get("positions"):
                _all = db.query(Position).filter_by(company_id=company_id).all()
                by_id = {p.id: p.name for p in _all}
                st.caption("Назначено для должностей: " + ", ".join(by_id.get(pid, str(pid)) for pid in ss.cl_add_form["positions"]))

            _ensure_first_section()
            sections = ss.cl_add_form["sections"]
            idx = ss.active_section_idx
            idx = max(0, min(idx, len(sections) - 1))
            ss.active_section_idx = idx
            sec = sections[idx]

            st.markdown("---")
            st.markdown(f"### Раздел {idx + 1}")
            sec_title = st.text_input("Название раздела", value=sec.get("title", ""), key=f"sec_title_{idx}")
            sec_desc = st.text_area("Описание (опционально)", value=sec.get("description", ""), key=f"sec_desc_{idx}")
            sec_req = st.checkbox("Обязательный раздел", value=bool(sec.get("is_required")), key=f"sec_req_{idx}")
            if st.button("Сохранить раздел", key=f"sec_save_{idx}"):
                sec["title"] = (sec_title or "").strip() or f"Раздел {idx + 1}"
                sec["description"] = (sec_desc or "").strip()
                sec["is_required"] = bool(sec_req)
                st.success("Раздел сохранен")
                st.rerun()

            # Список вопросов текущего раздела
            st.markdown("#### Вопросы раздела")
            qs: List[Dict] = sec.setdefault("questions", [])
            if qs:
                for n, q in enumerate(qs, 1):
                    suffix = ""
                    if ss.cl_add_form.get("is_scored") and q.get("weight") is not None:
                        suffix = f" (вес {q['weight']})"
                    st.markdown(f"{n}. {q['text']} - {q['type']}{suffix}")
                    if st.button("Удалить", key=f"q_del_{idx}_{n}"):
                        qs.pop(n - 1)
                        st.rerun()
            else:
                st.info("Пока нет вопросов. Добавьте первый вопрос.")

            # Форма добавления вопроса в текущий раздел
            st.markdown("**Добавить вопрос**")
            answer_types = ["Короткий текст", "Длинный текст", "Да/Нет", "Шкала (1-10)"]
            if ss.cl_add_form.get("is_scored"):
                answer_types = ["Да/Нет", "Шкала (1-10)"]
            with st.form(f"add_question_form_{idx}", clear_on_submit=True):
                q_text = st.text_input("Текст вопроса", key=f"q_text_{idx}")
                q_type = st.selectbox("Тип ответа", options=answer_types, key=f"q_type_{idx}")
                q_weight = None
                if ss.cl_add_form.get("is_scored") and q_type in ("Да/Нет", "Шкала (1-10)"):
                    q_weight = st.number_input("Вес вопроса (1-10)", min_value=1, max_value=10, value=1, key=f"q_weight_{idx}")
                req_photo = st.checkbox("Требовать фото", value=False, key=f"q_req_photo_{idx}")
                req_comment = st.checkbox("Требовать комментарий", value=False, key=f"q_req_comment_{idx}")
                q_required = st.checkbox("Обязательный вопрос?", value=True, key=f"q_required_{idx}")
                q_submit = st.form_submit_button("Добавить вопрос")
            if q_submit:
                txt = (q_text or "").strip()
                if not txt:
                    st.warning("Введите текст вопроса")
                else:
                    qs.append({
                        "text": txt,
                        "type": q_type,
                        "weight": int(q_weight) if (q_weight is not None) else None,
                        "require_photo": bool(req_photo),
                        "require_comment": bool(req_comment),
                        "required": bool(q_required),
                    })
                    st.success("Вопрос добавлен")
                    st.rerun()

            st.markdown("---")
            # Добавить новый раздел (становится активным)
            if st.button("Новый раздел", key=f"sec_new_{idx}"):
                sections.append({
                    "title": f"Раздел {len(sections) + 1}",
                    "description": "",
                    "is_required": False,
                    "questions": [],
                })
                ss.active_section_idx = len(sections) - 1
                st.rerun()

            # Кнопки навигации и сохранения
            c_back, c_save = st.columns([1, 2])
            with c_back:
                if st.button("Назад", key="add_back"):
                    ss.cl_add_step = 1
                    st.rerun()
            with c_save:
                if st.button("Сохранить чек-лист", key="add_save"):
                    try:
                        # Проверка дубля названия в пределах компании
                        existing = (
                            db.query(Checklist)
                            .filter_by(name=ss.cl_add_form["name"], company_id=company_id)
                            .first()
                        )
                        if existing:
                            st.warning("Чек-лист с таким названием уже существует.")
                            return

                        # Должности
                        pos_ids = ss.cl_add_form.get("positions", [])
                        assigned_positions = (
                            db.query(Position).filter(Position.id.in_(pos_ids)).all()
                            if pos_ids else []
                        )

                        # Создаем чек-лист
                        new_cl = Checklist(
                            name=ss.cl_add_form["name"],
                            company_id=company_id,
                            is_scored=ss.cl_add_form.get("is_scored", False),
                            created_by=0,  # TODO: проставить текущего пользователя
                            positions=assigned_positions,
                        )
                        db.add(new_cl)
                        db.commit()

                        # Создаем разделы и вопросы по порядку
                        q_type_map = {
                            "Да/Нет": "yesno",
                            "Шкала (1-10)": "scale",
                            "Короткий текст": "short_text",
                            "Длинный текст": "long_text",
                        }

                        for s_order, s in enumerate(ss.cl_add_form.get("sections", []), 1):
                            sec_obj = ChecklistSection(
                                checklist_id=new_cl.id,
                                title=(s.get("title") or f"Раздел {s_order}").strip(),
                                description=(s.get("description") or None),
                                order=s_order,
                                is_required=bool(s.get("is_required")),
                            )
                            db.add(sec_obj)
                            db.flush()

                            for q_order, q in enumerate(s.get("questions", []), 1):
                                meta = {"min": 1, "max": 10} if q.get("type") == "Шкала (1-10)" else None
                                db.add(
                                    ChecklistQuestion(
                                        checklist_id=new_cl.id,
                                        section_id=sec_obj.id,
                                        order=q_order,
                                        text=q.get("text"),
                                        type=q_type_map[q.get("type")],
                                        required=bool(q.get("required", True)),
                                        weight=(int(q.get("weight")) if q.get("weight") is not None else None),
                                        require_photo=bool(q.get("require_photo")),
                                        require_comment=bool(q.get("require_comment")),
                                        meta=meta,
                                    )
                                )

                        db.commit()
                        st.success("Чек-лист создан")

                        # Сброс мастера
                        ss.cl_add_form = {"name": "", "is_scored": False, "positions": [], "sections": []}
                        ss.cl_add_step = 1
                        ss.active_section_idx = 0
                        if dialog_state_key:
                            ss[dialog_state_key] = False
                        st.rerun()

                    except IntegrityError as e:
                        db.rollback()
                        st.error("Ошибка при сохранении чек-листа")
                        st.exception(e)

    finally:
        db.close()


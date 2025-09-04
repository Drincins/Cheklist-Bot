import streamlit as st 
import pandas as pd
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from sqlalchemy.orm import Session

from checklist.db.db import SessionLocal
from checklist.db.models import Checklist, ChecklistQuestion, Position
from checklist.admcompany.checklists_add import checklists_add_tab

# Метки типов ответов
_TYPE_LABELS = {
    "yesno": "Да/Нет/Пропустить",
    "scale": "Шкала (1–10)",
    "short_text": "Короткий текст",
    "long_text": "Длинный текст",
}
_TYPE_ORDER = ["yesno", "scale", "short_text", "long_text"]


def _type_label(code: str) -> str:
    return _TYPE_LABELS.get(code, code or "—")


def _remember_selected_checklist(cl: Checklist):
    """Запоминаем выбранный чек-лист в сессии."""
    st.session_state["cl_edit_selected_id"] = cl.id


def _remember_selected_question(q: ChecklistQuestion | None):
    """Запоминаем выбранный вопрос в сессии (или None)."""
    st.session_state["cl_edit_selected_qid"] = q.id if q else None


def _selected_checklist_index(checklists: list[Checklist]) -> int:
    """Вернуть индекс выбранного чек-листа по session_state, иначе 0."""
    cid = st.session_state.get("cl_edit_selected_id")
    if cid:
        for i, cl in enumerate(checklists):
            if cl.id == cid:
                return i
    return 0


def _selected_question_index(questions: list[ChecklistQuestion]) -> int:
    """Вернуть индекс выбранного вопроса по session_state, иначе 0."""
    qid = st.session_state.get("cl_edit_selected_qid")
    if qid:
        for i, q in enumerate(questions):
            if q.id == qid:
                return i
    return 0


def _reorder_questions(db: Session, checklist_id: int):
    """Переупорядочить вопросы после удаления, чтобы порядок был 1..N."""
    qs = (
        db.query(ChecklistQuestion)
        .filter_by(checklist_id=checklist_id)
        .order_by(ChecklistQuestion.order.asc(), ChecklistQuestion.id.asc())
        .all()
    )
    changed = False
    for idx, q in enumerate(qs, start=1):
        if q.order != idx:
            q.order = idx
            changed = True
    if changed:
        db.commit()


def _render_new_checklist_button(company_id: int):
    """
    Кнопка 'Новый чек-лист' с модалкой.
    ВАЖНО: передаём dialog_state_key внутрь checklists_add_tab, чтобы
    из формы добавления можно было:
      - по кнопке «Сохранить» -> вызвать st.rerun() (и обновить эту вкладку),
      - по своей кнопке «Закрыть» -> вызвать st.rerun() (и обновить эту вкладку).
    """
    _dialog = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)

    if _dialog:
        @_dialog("Создать чек-лист")
        def _add_checklist_dialog():
            # Внутри формы добавления:
            # - по успешному сохранению: st.rerun()
            # - по своей кнопке «Закрыть»: st.rerun()
            # (ключ "dlg_add_from_edit" используется только как маркер; закрытие делаем своей кнопкой)
            checklists_add_tab(company_id, embedded=True, dialog_state_key="dlg_add_from_edit")

        if st.button("🆕 Новый чек-лист", key="open_add_checklist_bottom", type="primary"):
            _add_checklist_dialog()
    else:
        if st.button("🆕 Новый чек-лист", key="open_add_checklist_fallback_bottom", type="primary"):
            st.info("Обнови Streamlit до 1.30+ для модального окна. Ниже показана форма добавления.")
            st.markdown("---")
            st.markdown("### Добавить чек-лист")
            # Фолбэк: без модалки. Всё равно передаём dialog_state_key — внутри будет st.rerun().
            checklists_add_tab(company_id, embedded=True, dialog_state_key="dlg_add_from_edit")


def checklists_edit_tab(company_id: int):
    db: Session = SessionLocal()
    try:
        st.subheader("Редактировать / Добавить чек-листы")

        # =========================
        # ФИЛЬТР ПО ДОЛЖНОСТЯМ
        # =========================
        all_positions = (
            db.query(Position)
            .filter_by(company_id=company_id)
            .order_by(Position.name.asc())
            .all()
        )
        pos_options = {p.name: p.id for p in all_positions}
        pos_names = list(pos_options.keys())

        st.markdown("#### Фильтр по должностям")
        sel_pos_names = st.multiselect(
            "Должности (необязательно, множественный выбор)",
            options=pos_names,
            default=[],
            key="cl_edit_pos_filter",
        )
        sel_pos_ids = {pos_options[n] for n in sel_pos_names} if sel_pos_names else set()

        # =========================
        # ВЫБОР ЧЕК-ЛИСТА
        # =========================
        q = (
            db.query(Checklist)
            .filter(Checklist.company_id == company_id)
            .options(joinedload(Checklist.positions))
            .order_by(Checklist.name.asc())
        )
        if sel_pos_ids:
            q = q.join(Checklist.positions).filter(Position.id.in_(sel_pos_ids)).distinct()

        checklists = q.all()
        if not checklists:
            st.info(
                "Нет чек-листов (по фильтру должностей ничего не найдено)."
                if sel_pos_ids
                else "В компании пока нет чек-листов."
            )
            # Нижняя панель (одна кнопка «Новый чек-лист»)
            st.markdown("---")
            cols = st.columns([6, 2, 2, 2])  # для красивого выравнивания вправо
            with cols[3]:
                _render_new_checklist_button(company_id)
            return

        # Подсчёт вопросов
        cl_id_to_qcount = {
            cl.id: db.query(ChecklistQuestion).filter_by(checklist_id=cl.id).count()
            for cl in checklists
        }
        # Метки (для краткой инфы)
        labels = [
            f"{cl.name} — {'оцениваемый' if cl.is_scored else 'без оценки'} · вопросов: {cl_id_to_qcount.get(cl.id, 0)}"
            for cl in checklists
        ]

        # Выбор чек-листа (стабильно удерживаем выбранный)
        default_idx = _selected_checklist_index(checklists)
        sel_idx = st.selectbox(
            "Редактируемый чек-лист:",
            options=list(range(len(checklists))),
            format_func=lambda i: labels[i],
            index=default_idx,
            key="cl_edit_select_idx",
        )
        selected_cl: Checklist = checklists[sel_idx]
        _remember_selected_checklist(selected_cl)

        # =========================
        # ТАБЛИЦА ВОПРОСОВ
        # =========================
        questions = (
            db.query(ChecklistQuestion)
            .filter_by(checklist_id=selected_cl.id)
            .order_by(ChecklistQuestion.order.asc())
            .all()
        )

        st.markdown("#### Вопросы чек-листа")
        if questions:
            rows = []
            for qobj in questions:
                rows.append(
                    {
                        "№": qobj.order,
                        "Вопрос": qobj.text or "",
                        "Тип ответа": _type_label(qobj.type),
                        "Фото обяз.": "Да" if (qobj.require_photo or False) else "Нет",
                        "Коммент обяз.": "Да" if (qobj.require_comment or False) else "Нет",
                        "Вес": int(qobj.weight) if (qobj.weight is not None) else "",
                    }
                )
            df = pd.DataFrame(
                rows, columns=["№", "Вопрос", "Тип ответа", "Фото обяз.", "Коммент обяз.", "Вес"]
            )
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("В этом чек-листе пока нет вопросов.")

        st.markdown("---")

        # =========================
        # НИЖНЯЯ ПАНЕЛЬ: 3 КНОПКИ
        # =========================
        btn_cols = st.columns([6, 2, 2, 2])  # выравниваем вправо
        # 1) ✏️ Редактировать вопрос (popover)
        with btn_cols[1]:
            with st.popover("✏️ Редактировать вопрос", use_container_width=True):
                if not questions:
                    st.info("Вопросов нет. Сначала добавьте новый вопрос или создайте чек-лист.")
                else:
                    # Выбор вопроса (удерживаем выбранный)
                    q_labels = [f"{q.order}. {q.text[:60]}" for q in questions]
                    default_q_idx = _selected_question_index(questions)
                    sel_q_idx = st.selectbox(
                        "Выберите вопрос:",
                        options=list(range(len(questions))),
                        format_func=lambda i: q_labels[i],
                        index=default_q_idx,
                        key="cl_edit_q_select_idx",
                    )
                    q_edit: ChecklistQuestion = questions[sel_q_idx]
                    _remember_selected_question(q_edit)

                    # Поля редактирования
                    new_text = st.text_input(
                        "Текст вопроса", value=q_edit.text or "", key=f"q_text_{q_edit.id}"
                    )
                    new_type = st.selectbox(
                        "Тип ответа",
                        options=_TYPE_ORDER,
                        format_func=_type_label,
                        index=_TYPE_ORDER.index(q_edit.type) if q_edit.type in _TYPE_ORDER else 0,
                        key=f"q_type_{q_edit.id}",
                    )
                    new_weight = st.number_input(
                        "Вес (1–10, если применимо)",
                        min_value=1,
                        max_value=10,
                        value=int(q_edit.weight) if q_edit.weight is not None else 1,
                        key=f"q_weight_{q_edit.id}",
                    )
                    c_photo, c_comm = st.columns(2)
                    with c_photo:
                        req_photo = st.checkbox(
                            "Обязательное фото", value=bool(q_edit.require_photo), key=f"q_req_photo_{q_edit.id}"
                        )
                    with c_comm:
                        req_comment = st.checkbox(
                            "Обязательный комментарий", value=bool(q_edit.require_comment), key=f"q_req_comm_{q_edit.id}"
                        )

                    col_a, col_b = st.columns(2)
                    with col_a:
                        if st.button("💾 Сохранить изменения", key=f"save_q_{q_edit.id}"):
                            try:
                                q_edit.text = new_text
                                q_edit.type = new_type
                                q_edit.weight = int(new_weight) if new_weight else None
                                q_edit.require_photo = bool(req_photo)
                                q_edit.require_comment = bool(req_comment)
                                db.commit()
                                # Удерживаем текущий выбор
                                _remember_selected_checklist(selected_cl)
                                _remember_selected_question(q_edit)
                                st.success("Вопрос обновлён")
                                st.rerun()
                            except IntegrityError as e:
                                db.rollback()
                                st.error("Ошибка при сохранении вопроса")
                                st.exception(e)
                    with col_b:
                        if st.button("🗑️ Удалить вопрос", key=f"del_q_{q_edit.id}"):
                            try:
                                # вычисляем соседа для выбора после удаления
                                next_q_id = None
                                if len(questions) > 1:
                                    cur_i = sel_q_idx
                                    if cur_i < len(questions) - 1:
                                        next_q_id = questions[cur_i + 1].id
                                    else:
                                        next_q_id = questions[cur_i - 1].id
                                db.delete(q_edit)
                                db.commit()
                                _reorder_questions(db, selected_cl.id)
                                # Удерживаем текущий чек-лист и новый выбранный вопрос
                                _remember_selected_checklist(selected_cl)
                                if next_q_id:
                                    nq = db.query(ChecklistQuestion).filter_by(id=next_q_id).first()
                                    _remember_selected_question(nq)
                                else:
                                    _remember_selected_question(None)

                                st.success("Вопрос удалён")
                                st.rerun()
                            except IntegrityError as e:
                                db.rollback()
                                st.error("Ошибка при удалении вопроса")
                                st.exception(e)

        # 2) ➕ Добавить вопрос (popover)
        with btn_cols[2]:
            with st.popover("➕ Добавить вопрос", use_container_width=True):
                new_q_text = st.text_input("Текст вопроса", key="add_q_text_pop")
                new_q_type = st.selectbox(
                    "Тип ответа", options=_TYPE_ORDER, format_func=_type_label, index=0, key="add_q_type_pop"
                )
                new_q_weight = st.number_input("Вес (1–10, если применимо)", min_value=1, max_value=10, value=1, key="add_q_weight_pop")
                c1, c2 = st.columns(2)
                with c1:
                    new_req_photo = st.checkbox("Обязательное фото", value=False, key="add_q_req_photo_pop")
                with c2:
                    new_req_comment = st.checkbox("Обязательный комментарий", value=False, key="add_q_req_comment_pop")

                if st.button("✅ Добавить", key="add_q_submit_pop", type="primary"):
                    if not new_q_text.strip():
                        st.error("Введите текст вопроса")
                    else:
                        try:
                            # order = последний + 1
                            last = (
                                db.query(ChecklistQuestion)
                                .filter_by(checklist_id=selected_cl.id)
                                .order_by(ChecklistQuestion.order.desc())
                                .first()
                            )
                            new_order = (last.order + 1) if last else 1
                            new_q = ChecklistQuestion(
                                checklist_id=selected_cl.id,
                                order=new_order,
                                text=new_q_text.strip(),
                                type=new_q_type,
                                required=True,
                                weight=int(new_q_weight) if new_q_weight else None,
                                require_photo=bool(new_req_photo),
                                require_comment=bool(new_req_comment),
                            )
                            db.add(new_q)
                            db.commit()
                            # Удерживаем выбор чек-листа и выбрать только что созданный вопрос
                            _remember_selected_checklist(selected_cl)
                            _remember_selected_question(new_q)
                            st.success("Вопрос добавлен")
                            st.rerun()
                        except IntegrityError as e:
                            db.rollback()
                            st.error("Ошибка при добавлении вопроса")
                            st.exception(e)

        # 3) 🆕 Новый чек-лист (модалка)
        with btn_cols[3]:
            _render_new_checklist_button(company_id)

    finally:
        db.close()

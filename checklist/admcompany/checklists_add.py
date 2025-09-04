# checklist/admcompany/checklists_add.py
import streamlit as st
from typing import Optional
from checklist.db.db import SessionLocal
from checklist.db.models import Checklist, ChecklistQuestion, Position
from sqlalchemy.exc import IntegrityError


def checklists_add_tab(company_id: int, embedded: bool = False, dialog_state_key: Optional[str] = None):
    """
    Мастер добавления чек-листа в 2 шага:
      1) Основные настройки (название, тип, должности)
      2) Добавление вопросов и сохранение

    Что важно:
    - Без кастомного CSS.
    - Удаление вопросов — мгновенная перерисовка (через nonce).
    - Поля формы «Добавить вопрос» очищаются сразу (clear_on_submit=True).
    - Если передан dialog_state_key (модалка), то:
        * По «Закрыть» — закрываем модалку и делаем st.rerun().
        * После успешного сохранения — закрываем модалку и st.rerun()
          (вкладка редактирования сразу увидит новый чек-лист).
    """
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
                "questions": [],   # [{text,type,weight,require_photo,require_comment}, ...]
                "positions": [],   # [position_id, ...]
            }
        # nonce — используем только для мгновенной перерисовки списка вопросов при удалении
        if "cl_add_nonce" not in ss:
            ss.cl_add_nonce = 0

        # Кнопка «Закрыть» в модалке (если открыты внутри dialog)
        if embedded:
            if st.button("✖ Закрыть", key="cl_add_close"):
                if dialog_state_key:
                    ss[dialog_state_key] = False
                st.rerun()

        # =========================================================
        # ШАГ 1: Основные настройки чек-листа
        # =========================================================
        if ss.cl_add_step == 1:
            with st.form("create_checklist_form", clear_on_submit=False):
                name = st.text_input(
                    "Название чек-листа",
                    value=ss.cl_add_form["name"],
                    key="cl_add_name_input",
                )
                is_scored = st.checkbox(
                    "Оцениваемый чек-лист?",
                    value=ss.cl_add_form["is_scored"],
                    key="cl_add_is_scored",
                )

                # Должности компании
                all_positions = (
                    db.query(Position)
                    .filter_by(company_id=company_id)
                    .order_by(Position.name.asc())
                    .all()
                )
                selected_pos_ids = ss.cl_add_form.get("positions", [])
                pos_options = {}
                default_names = []
                if all_positions:
                    pos_options = {p.name: p.id for p in all_positions}
                    default_names = [p.name for p in all_positions if p.id in selected_pos_ids]
                    selected_pos_names = st.multiselect(
                        "Для должностей (множественный выбор)",
                        options=list(pos_options.keys()),
                        default=default_names,
                        key="add_step1_pos_multiselect",
                    )
                    selected_pos_ids = [pos_options[name] for name in selected_pos_names]
                else:
                    st.info("Сначала добавьте должности в компании, чтобы назначить доступ к чек-листу.")

                submit = st.form_submit_button("Создать и перейти к вопросам ➡️")

            if submit:
                if not name.strip():
                    st.error("Введите название чек-листа")
                else:
                    ss.cl_add_form["name"] = name.strip()
                    ss.cl_add_form["is_scored"] = bool(is_scored)
                    ss.cl_add_form["positions"] = selected_pos_ids
                    ss.cl_add_step = 2
                    # без st.rerun()

        # =========================================================
        # ШАГ 2: Добавление вопросов и сохранение
        # =========================================================
        if ss.cl_add_step == 2:
            st.markdown(f"**Чек-лист:** {ss.cl_add_form['name']}")
            is_scored = ss.cl_add_form["is_scored"]
            st.write("Тип: " + ("Оцениваемый" if is_scored else "Без оценки"))

            # Показ выбранных должностей
            if ss.cl_add_form.get("positions"):
                _all = db.query(Position).filter_by(company_id=company_id).all()
                by_id = {p.id: p.name for p in _all}
                chosen = [by_id.get(pid, f"id={pid}") for pid in ss.cl_add_form["positions"]]
                st.caption("Назначено для должностей: " + ", ".join(chosen))

            st.markdown("### Добавьте вопросы")

            # Типы ответа
            answer_types = (
                ["Да/Нет/Пропустить", "Шкала (1-10)"]
                if is_scored
                else ["Короткий текст", "Длинный текст", "Да/Нет/Пропустить", "Шкала (1-10)"]
            )

            # --- Форма добавления вопроса ---
            # ВАЖНО: clear_on_submit=True — поля очищаются сразу после успешного сабмита
            with st.form("add_question_form", clear_on_submit=True):
                q_text = st.text_input("1) Вопрос", key="add_q_text", value="")
                q_type = st.selectbox(
                    "2) Тип ответа",
                    answer_types,
                    index=0 if answer_types else None,
                    key="add_q_type",
                )

                q_weight = None
                if is_scored and q_type in ["Да/Нет/Пропустить", "Шкала (1-10)"]:
                    q_weight = st.number_input(
                        "3) Вес вопроса (1–10)",
                        min_value=1, max_value=10,
                        value=1,
                        key="add_q_weight",
                    )

                req_photo = st.checkbox(
                    "4) Обязательно приложить фотографию",
                    value=False,
                    key="add_req_photo",
                )
                req_comment = st.checkbox(
                    "5) Обязательно дополнить ответ комментарием",
                    value=False,
                    key="add_req_comment",
                )

                q_submit = st.form_submit_button("➕ Добавить вопрос")

            # Добавление вопроса
            if q_submit:
                txt = (st.session_state.get("add_q_text") or "").strip()
                if not txt:
                    st.warning("Введите текст вопроса")
                else:
                    ss.cl_add_form["questions"].append(
                        {
                            "text": txt,
                            "type": st.session_state.get("add_q_type"),
                            "weight": (int(st.session_state.get("add_q_weight", 1))
                                       if (is_scored and st.session_state.get("add_q_type") in ["Да/Нет/Пропустить", "Шкала (1-10)"])
                                       else None),
                            "require_photo": bool(st.session_state.get("add_req_photo")),
                            "require_comment": bool(st.session_state.get("add_req_comment")),
                        }
                    )
                    st.success("Вопрос добавлен")
                    # Поля очищены самим формом (clear_on_submit=True)

            # Список вопросов + удаление (мгновенная перерисовка за счёт nonce)
            if ss.cl_add_form["questions"]:
                st.markdown("#### Вопросы чек-листа:")
                nonce = ss.cl_add_nonce  # для уникальности ключей кнопок
                for idx, q in enumerate(ss.cl_add_form["questions"]):
                    num = idx + 1
                    extras = []
                    if q.get("weight"):
                        extras.append(f"вес {q['weight']}")
                    if q.get("require_photo"):
                        extras.append("фото обязательно")
                    if q.get("require_comment"):
                        extras.append("комментарий обязателен")
                    suffix = f" ({', '.join(extras)})" if extras else ""
                    c_txt, c_del = st.columns([0.95, 0.05])
                    with c_txt:
                        st.markdown(f"{num}. **{q['text']}** — {q['type']}{suffix}")
                    with c_del:
                        if st.button("✖", key=f"del_draft_q_{nonce}_{num}", help="Удалить вопрос"):
                            del ss.cl_add_form["questions"][idx]
                            ss.cl_add_nonce += 1  # форс обновление списка
                            st.toast("Вопрос удалён")

            # Кнопки навигации / сохранения
            c1, c2 = st.columns(2)
            with c1:
                if st.button("⬅️ Назад", key=f"add_back_{ss.cl_add_nonce}"):
                    ss.cl_add_step = 1  # без rerun
            with c2:
                if st.button("💾 Сохранить чек-лист", key=f"add_save_checklist_{ss.cl_add_nonce}"):
                    if not ss.cl_add_form["questions"]:
                        st.error("Добавьте хотя бы один вопрос")
                    else:
                        try:
                            # Проверка на дубликат имени в рамках компании
                            existing = (
                                db.query(Checklist)
                                .filter_by(name=ss.cl_add_form["name"], company_id=company_id)
                                .first()
                            )
                            if existing:
                                st.warning("Такой чек-лист уже существует.")
                            else:
                                # Привязка должностей
                                pos_ids = ss.cl_add_form["positions"]
                                assigned_positions = (
                                    db.query(Position).filter(Position.id.in_(pos_ids)).all()
                                    if pos_ids else []
                                )

                                # Создаём чек-лист
                                new_cl = Checklist(
                                    name=ss.cl_add_form["name"],
                                    company_id=company_id,
                                    is_scored=ss.cl_add_form["is_scored"],
                                    created_by=0,  # TODO: текущий админ
                                    positions=assigned_positions,
                                )
                                db.add(new_cl)
                                db.commit()

                                # Типы → внутренние коды БД
                                q_type_map = {
                                    "Да/Нет/Пропустить": "yesno",
                                    "Шкала (1-10)": "scale",
                                    "Короткий текст": "short_text",
                                    "Длинный текст": "long_text",
                                }

                                # Вставка вопросов
                                for order_idx, q in enumerate(ss.cl_add_form["questions"], 1):
                                    db.add(
                                        ChecklistQuestion(
                                            checklist_id=new_cl.id,
                                            order=order_idx,
                                            text=q["text"],
                                            type=q_type_map[q["type"]],
                                            required=True,
                                            weight=(int(q["weight"]) if q.get("weight") is not None else None),
                                            require_photo=bool(q.get("require_photo")),
                                            require_comment=bool(q.get("require_comment")),
                                        )
                                    )
                                db.commit()

                                st.success("Чек-лист и вопросы успешно сохранены!")
                                # Сброс мастера и nonce
                                ss.cl_add_form = {
                                    "name": "",
                                    "is_scored": False,
                                    "questions": [],
                                    "positions": [],
                                }
                                ss.cl_add_step = 1
                                ss.cl_add_nonce = 0

                                # Если внутри модалки — закрываем и форсим обновление всей страницы
                                if dialog_state_key:
                                    ss[dialog_state_key] = False
                                st.rerun()

                        except IntegrityError as e:
                            db.rollback()
                            st.error("Ошибка при добавлении чек-листа")
                            st.exception(e)
    finally:
        db.close()

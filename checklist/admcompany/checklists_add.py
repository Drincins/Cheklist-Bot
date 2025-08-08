import streamlit as st
from checklist.db.db import SessionLocal
from checklist.db.models import Checklist, ChecklistQuestion, Position
from sqlalchemy.exc import IntegrityError

def checklists_add_tab(company_id):
    db = SessionLocal()
    try:
        st.subheader("Добавить чек-лист")

        # Шаг/форма в session_state
        if "cl_add_step" not in st.session_state:
            st.session_state.cl_add_step = 1
        if "cl_add_form" not in st.session_state:
            st.session_state.cl_add_form = {
                "name": "",
                "is_scored": False,
                "questions": [],
                "positions": []
            }

        # --- Шаг 1: основные настройки чек-листа ---
        if st.session_state.cl_add_step == 1:
            with st.form("create_checklist_form"):
                name = st.text_input(
                    "Название чек-листа",
                    value=st.session_state.cl_add_form["name"]
                )
                is_scored = st.checkbox(
                    "Оцениваемый чек-лист?",
                    value=st.session_state.cl_add_form["is_scored"]
                )

                # Множественный выбор должностей
                all_positions = (
                    db.query(Position)
                    .filter_by(company_id=company_id)
                    .order_by(Position.name.asc())
                    .all()
                )
                selected_pos_ids = st.session_state.cl_add_form.get("positions", [])
                pos_options = {}
                default_names = []

                if all_positions:
                    pos_options = {p.name: p.id for p in all_positions}
                    default_names = [p.name for p in all_positions if p.id in selected_pos_ids]
                    selected_pos_names = st.multiselect(
                        "Для должностей (множественный выбор)",
                        options=list(pos_options.keys()),
                        default=default_names,
                        key="add_step1_pos_multiselect"
                    )
                    selected_pos_ids = [pos_options[name] for name in selected_pos_names]
                else:
                    st.info("Сначала добавьте должности в компании, чтобы назначить доступ к чек-листу.")

                # ВАЖНО: submit всегда внутри формы и вне if/else
                submit = st.form_submit_button("Создать и перейти к добавлению вопросов ➡️")

            if submit:
                if not name:
                    st.error("Введите название чек-листа")
                else:
                    st.session_state.cl_add_form["name"] = name
                    st.session_state.cl_add_form["is_scored"] = is_scored
                    st.session_state.cl_add_form["positions"] = selected_pos_ids
                    st.session_state.cl_add_step = 2
                    st.rerun()

        # --- Шаг 2: добавление вопросов и сохранение ---
        if st.session_state.cl_add_step == 2:
            st.markdown(f"**Чек-лист:** {st.session_state.cl_add_form['name']}")
            is_scored = st.session_state.cl_add_form["is_scored"]
            st.write("Тип: " + ("Оцениваемый" if is_scored else "Без оценки"))

            # Показать выбранные должности (read-only)
            if st.session_state.cl_add_form.get("positions"):
                all_positions = db.query(Position).filter_by(company_id=company_id).all()
                by_id = {p.id: p.name for p in all_positions}
                chosen = [by_id.get(pid, f"id={pid}") for pid in st.session_state.cl_add_form["positions"]]
                st.caption("Назначено для должностей: " + ", ".join(chosen))

            st.markdown("### Добавьте вопросы:")

            # Текущие типы проекта
            answer_types = (
                ["Да/Нет/Пропустить", "Шкала (1-10)"]
                if is_scored else
                ["Короткий текст", "Длинный текст", "Да/Нет/Пропустить", "Шкала (1-10)"]
            )

            with st.form("add_question_form"):
                q_text = st.text_input("1) Вопрос", key="add_q_text")
                q_type = st.selectbox("2) Тип ответа", answer_types, key="add_q_type")

                # Вес — только если оцениваемый и тип релевантен
                q_weight = None
                if is_scored and q_type in ["Да/Нет/Пропустить", "Шкала (1-10)"]:
                    q_weight = st.number_input(
                        "3) Вес вопроса (1–10)",
                        min_value=1,
                        max_value=10,
                        value=1,
                        key="add_q_weight"
                    )

                # Новые флаги требований (теперь это реальные поля в БД)
                req_photo = st.checkbox("4) Обязательно приложить фотографию", value=False, key="add_req_photo")
                req_comment = st.checkbox("5) Обязательно дополнить ответ комментарием", value=False, key="add_req_comment")

                q_submit = st.form_submit_button("➕ Добавить вопрос")
                if q_submit:
                    if not q_text:
                        st.error("Введите текст вопроса")
                    else:
                        st.session_state.cl_add_form["questions"].append({
                            "text": q_text,
                            "type": q_type,
                            "weight": int(q_weight) if q_weight else None,
                            "require_photo": bool(req_photo),
                            "require_comment": bool(req_comment),
                        })
                        st.rerun()

            if st.session_state.cl_add_form["questions"]:
                st.markdown("#### Вопросы чек-листа:")
                for idx, q in enumerate(st.session_state.cl_add_form["questions"], 1):
                    add = []
                    if q.get("weight"):
                        add.append(f"вес {q['weight']}")
                    if q.get("require_photo"):
                        add.append("фото обязательно")
                    if q.get("require_comment"):
                        add.append("комментарий обязателен")
                    suffix = f" ({', '.join(add)})" if add else ""
                    st.markdown(f"{idx}. {q['text']} — {q['type']}{suffix}")

            c1, c2 = st.columns(2)
            with c1:
                if st.button("⬅️ Назад", key="add_back"):
                    st.session_state.cl_add_step = 1
                    st.rerun()
            with c2:
                if st.button("💾 Сохранить чек-лист", key="add_save_checklist"):
                    if not st.session_state.cl_add_form["questions"]:
                        st.error("Добавьте хотя бы один вопрос")
                    else:
                        try:
                            # Проверка дубликата по имени в рамках компании
                            existing_cl = (
                                db.query(Checklist)
                                .filter_by(name=st.session_state.cl_add_form["name"], company_id=company_id)
                                .first()
                            )
                            if existing_cl:
                                st.warning("Такой чек-лист уже существует.")
                            else:
                                # Создаём чек-лист и назначаем должности
                                pos_ids = st.session_state.cl_add_form["positions"]
                                assigned_positions = (
                                    db.query(Position).filter(Position.id.in_(pos_ids)).all()
                                    if pos_ids else []
                                )

                                new_cl = Checklist(
                                    name=st.session_state.cl_add_form["name"],
                                    company_id=company_id,
                                    is_scored=st.session_state.cl_add_form["is_scored"],
                                    created_by=0,  # TODO: подставить текущего админа, если используете auth
                                    positions=assigned_positions
                                )
                                db.add(new_cl)
                                db.commit()

                                # Типы → внутренние коды
                                q_type_map = {
                                    "Да/Нет/Пропустить": "yesno",
                                    "Шкала (1-10)": "scale",
                                    "Короткий текст": "short_text",
                                    "Длинный текст": "long_text",
                                }

                                # Сохраняем вопросы (НОВЫЕ ПОЛЯ: weight/require_photo/require_comment)
                                for idx, q in enumerate(st.session_state.cl_add_form["questions"], 1):
                                    db.add(
                                        ChecklistQuestion(
                                            checklist_id=new_cl.id,
                                            order=idx,
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
                                # Сброс формы
                                st.session_state.cl_add_form = {
                                    "name": "",
                                    "is_scored": False,
                                    "questions": [],
                                    "positions": []
                                }
                                st.session_state.cl_add_step = 1
                                st.rerun()

                        except IntegrityError as e:
                            db.rollback()
                            st.error("Ошибка при добавлении чек-листа")
                            st.exception(e)
    finally:
        db.close()

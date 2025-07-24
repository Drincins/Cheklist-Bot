import streamlit as st
from checklist.db import SessionLocal
from checklist.models import Checklist, ChecklistQuestion,Position
from sqlalchemy.exc import IntegrityError

def add_checklist_tab(company_id):
    db = SessionLocal()
    st.subheader("Добавить новый чек-лист (по шагам)")
    if "cl_step" not in st.session_state:
        st.session_state.cl_step = 1
    if "cl_form" not in st.session_state:
        st.session_state.cl_form = {
            "name": "",
            "is_scored": False,
            "questions": []
        }

    # --- ШАГ 1: Название и тип чек-листа ---
    if st.session_state.cl_step == 1:
        name = st.text_input("Название чек-листа", value=st.session_state.cl_form["name"])
        is_scored = st.checkbox("Оцениваемый чек-лист?", value=st.session_state.cl_form["is_scored"])
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Далее ➡️"):
                if not name:
                    st.error("Введите название чек-листа")
                else:
                    st.session_state.cl_form["name"] = name
                    st.session_state.cl_form["is_scored"] = is_scored
                    st.session_state.cl_step = 2
        with col2:
            if st.button("↩️ Назад"):
                st.session_state.cl_form = {
                    "name": "",
                    "is_scored": False,
                    "questions": [],
                    "positions": []
                }
                st.session_state.cl_step = 1

    # --- ШАГ 2: Добавление вопросов ---
    if st.session_state.cl_step == 2:
        st.write(f"**Чек-лист:** {st.session_state.cl_form['name']}")
        is_scored = st.session_state.cl_form["is_scored"]
        st.write("Тип: " + ("Оцениваемый" if is_scored else "Без оценки"))
        st.markdown("**Добавьте вопросы к чек-листу:**")

        if is_scored:
            answer_types = ["Да/Нет/Пропустить", "Шкала (1-10)"]
        else:
            answer_types = ["Короткий текст", "Длинный текст", "Да/Нет/Пропустить", "Шкала (1-10)"]

        with st.form("add_question_form"):
            q_text = st.text_input("Текст вопроса")
            q_type = st.selectbox("Тип ответа", answer_types)
            q_weight = None
            if is_scored and q_type in ["Да/Нет/Пропустить", "Шкала (1-10)"]:
                q_weight = st.number_input("Вес вопроса (от 1 до 10)", min_value=1, max_value=10, value=1)
            q_submit = st.form_submit_button("Добавить вопрос")
            if q_submit:
                if not q_text:
                    st.error("Введите текст вопроса")
                else:
                    st.session_state.cl_form["questions"].append({
                        "text": q_text,
                        "type": q_type,
                        "weight": int(q_weight) if q_weight else None
                    })
                    st.rerun()
             # === Привязка чек-листа к должностям ===
        st.markdown("### 👥 Назначить чек-лист должностям")

        all_positions = db.query(Position).filter_by(company_id=company_id).all()
        if all_positions:
            pos_options = {p.name: p.id for p in all_positions}

            selected_pos_names = st.multiselect(
                "Выберите должности",
                options=list(pos_options.keys()),
                default=[
                    name for name in pos_options.keys()
                    if pos_options[name] in st.session_state.cl_form.get("positions", [])
                ],
                key="create_pos_multiselect"
            )
            st.session_state.cl_form["positions"] = [pos_options[name] for name in selected_pos_names]
        else:
            st.info("В компании пока нет должностей. Вы можете назначить их позже.")

        if st.session_state.cl_form["questions"]:
            st.markdown("#### Вопросы чек-листа:")
            for idx, q in enumerate(st.session_state.cl_form["questions"], 1):
                st.markdown(
                    f"{idx}. {q['text']} — {q['type']}"
                    + (f" (вес: {q['weight']})" if q.get("weight") else "")
                )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("⬅️ Назад", key="back_questions"):
                st.session_state.cl_step = 1
        with col2:
            if st.button("💾 Сохранить чек-лист", key="save_checklist"):
                if not st.session_state.cl_form["questions"]:
                    st.error("Добавьте хотя бы один вопрос")
                else:
                    try:
                        existing_cl = db.query(Checklist).filter_by(
                            name=st.session_state.cl_form["name"],
                            company_id=company_id
                        ).first()
                        if existing_cl:
                            st.warning("Такой чек-лист уже существует.")
                        else:
                            # Получаем объекты должностей
                            assigned_positions = db.query(Position).filter(Position.id.in_(
                                st.session_state.cl_form["positions"]
                            )).all()

                            new_cl = Checklist(
                                name=st.session_state.cl_form["name"],
                                is_scored=st.session_state.cl_form["is_scored"],
                                company_id=company_id,
                                created_by=1,  # TODO: заменить на текущего пользователя
                                positions=assigned_positions  # <-- Сразу назначаем
                            )

                            db.add(new_cl)
                            db.commit()
                            q_type_map = {
                                "Да/Нет/Пропустить": "yesno",
                                "Шкала (1-10)": "scale",
                                "Короткий текст": "short_text",
                                "Длинный текст": "long_text"
                            }
                            for idx, q in enumerate(st.session_state.cl_form["questions"], 1):
                                db.add(
                                    ChecklistQuestion(
                                        checklist_id=new_cl.id,
                                        order=idx,
                                        text=q["text"],
                                        type=q_type_map[q["type"]],
                                        required=True,
                                        meta={"weight": q["weight"]} if q.get("weight") else None
                                    )
                                )
                            db.commit()
                            st.success("Чек-лист и вопросы успешно сохранены!")
                            st.session_state.cl_form = {"name": "", "is_scored": False, "questions": [],"positions": []}
                            st.session_state.cl_step = 1
                            st.rerun()
                    except IntegrityError as e:
                        db.rollback()
                        st.error("Ошибка при добавлении чек-листа")
                        st.exception(e)
    db.close()

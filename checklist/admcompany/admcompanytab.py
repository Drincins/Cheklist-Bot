import streamlit as st
from checklist.db import SessionLocal
from checklist.models import User, Checklist, ChecklistQuestion
from sqlalchemy.exc import IntegrityError

def company_admin_dashboard(company_id):
    st.title("👨‍💼 Панель администратора компании")
    db = SessionLocal()

    tabs = st.tabs(["Сотрудники", "Добавить сотрудника", "Чек-листы", "Добавить чек-лист"])

    # ——— TAB 1 ——— Просмотр сотрудников
    with tabs[0]:
        st.subheader("Список сотрудников")
        users = db.query(User).filter_by(company_id=company_id, role="employee").all()
        if users:
            for u in users:
                st.write(f"- {u.name}")
        else:
            st.info("Сотрудников пока нет.")

    # ——— TAB 2 ——— Добавление нового сотрудника
    with tabs[1]:
        st.subheader("Добавление нового сотрудника")
        with st.form("add_user_form"):
            last_name = st.text_input("Фамилия")
            first_name = st.text_input("Имя")
            col1, col2 = st.columns([1, 5])
            with col1:
                st.markdown("### +7")
            with col2:
                raw_phone = st.text_input("Телефон (10 цифр)", max_chars=10)
            position = st.text_input("Должность (пока текстовое поле)")
            submitted = st.form_submit_button("Добавить")
            if submitted:
                if not (last_name and first_name and raw_phone and position):
                    st.error("Пожалуйста, заполните все поля")
                elif not raw_phone.isdigit() or len(raw_phone) != 10:
                    st.error("Телефон должен содержать ровно 10 цифр")
                else:
                    phone = "+7" + raw_phone
                    full_name = f"{last_name} {first_name}"
                    existing = db.query(User).filter_by(phone=phone, company_id=company_id).first()
                    if existing:
                        st.warning("Сотрудник с таким номером телефона уже существует.")
                    else:
                        new_user = User(
                            name=full_name,
                            phone=phone,
                            role="employee",
                            login=None,
                            hashed_password=None,
                            company_id=company_id,
                            position_id=None  # пока без справочника
                        )
                        db.add(new_user)
                        try:
                            db.commit()
                            st.success(f"Сотрудник {full_name} успешно добавлен")
                        except IntegrityError as e:
                            db.rollback()
                            st.error("Ошибка при добавлении сотрудника")
                            st.exception(e)

    # ——— TAB 3 ——— Просмотр чек-листов
    with tabs[2]:
        st.subheader("Чек-листы компании")
        checklists = db.query(Checklist).filter_by(company_id=company_id).all()
        if checklists:
            for cl in checklists:
                st.write(f"- {cl.name}")
        else:
            st.info("Чек-листов пока нет.")

    # ——— TAB 4 ——— Добавление чек-листа с вопросами
    with tabs[3]:
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
                        "questions": []
                    }
                    st.session_state.cl_step = 1

        # --- ШАГ 2: Добавление вопросов ---
        if st.session_state.cl_step == 2:
            st.write(f"**Чек-лист:** {st.session_state.cl_form['name']}")
            is_scored = st.session_state.cl_form["is_scored"]
            st.write("Тип: " + ("Оцениваемый" if is_scored else "Без оценки"))
            st.markdown("**Добавьте вопросы к чек-листу:**")

            # Типы вопросов в зависимости от чек-листа
            if is_scored:
                answer_types = ["Да/Нет/Пропустить", "Шкала (1-10)"]
            else:
                answer_types = ["Короткий текст", "Длинный текст", "Да/Нет/Пропустить", "Шкала (1-10)"]

            # Форма добавления одного вопроса
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

            # Список добавленных вопросов
            if st.session_state.cl_form["questions"]:
                st.markdown("#### Вопросы чек-листа:")
                for idx, q in enumerate(st.session_state.cl_form["questions"], 1):
                    st.markdown(
                        f"{idx}. {q['text']} — {q['type']}"
                        + (f" (вес: {q['weight']})" if q.get("weight") else "")
                    )

            # Управляющие кнопки
            col1, col2 = st.columns(2)
            with col1:
                if st.button("⬅️ Назад", key="back_questions"):
                    st.session_state.cl_step = 1
            with col2:
                if st.button("💾 Сохранить чек-лист", key="save_checklist"):
                    # Проверка перед сохранением
                    if not st.session_state.cl_form["questions"]:
                        st.error("Добавьте хотя бы один вопрос")
                    else:
                        # Сохраняем чек-лист и вопросы
                        try:
                            # Проверка на дубликат
                            existing_cl = db.query(Checklist).filter_by(
                                name=st.session_state.cl_form["name"],
                                company_id=company_id
                            ).first()
                            if existing_cl:
                                st.warning("Такой чек-лист уже существует.")
                            else:
                                new_cl = Checklist(
                                    name=st.session_state.cl_form["name"],
                                    is_scored=st.session_state.cl_form["is_scored"],
                                    company_id=company_id,
                                    created_by=1,  # ID текущего админа, замени как нужно
                                )
                                db.add(new_cl)
                                db.commit()
                                # Вопросы
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
                                st.session_state.cl_form = {"name": "", "is_scored": False, "questions": []}
                                st.session_state.cl_step = 1
                                st.rerun()
                        except IntegrityError as e:
                            db.rollback()
                            st.error("Ошибка при добавлении чек-листа")
                            st.exception(e)


    db.close()

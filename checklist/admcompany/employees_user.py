# checklist/admcompany/employees_user.py
# Вкладка «Сотрудники»: таблица (без ID), добавление, редактирование,
# удаление (двухкликовое подтверждение через session_state) + ЛОГИН/ПАРОЛЬ.

from __future__ import annotations

import streamlit as st
import pandas as pd
from typing import Optional
import bcrypt  # хешируем веб‑пароли

from checklist.db.db import SessionLocal
from checklist.db.models import (
    User, Department, Position,
    ChecklistAnswer, ChecklistQuestionAnswer,
)


# ==========================
#        HELPERS
# ==========================
def _get_current_user(db) -> Optional[User]:
    uid = st.session_state.get("user_id")
    if uid:
        return db.query(User).get(int(uid))
    tg_id = st.session_state.get("telegram_id")
    if tg_id:
        return db.query(User).filter(User.telegram_id == int(tg_id)).first()
    return None


def _is_admin(user: Optional[User]) -> bool:
    sr = str(st.session_state.get("user_role", "") or "").strip().lower()
    if sr in {"admin", "администратор", "administrator", "главный администратор"}:
        return True
    if not user or not user.position or not user.position.role:
        return False
    try:
        role_name = (user.position.role.name or "").strip().lower()
        return role_name in {"admin", "администратор", "administrator", "главный администратор"}
    except Exception:
        return False


def _users_in_same_departments(db, viewer: User, company_id: int) -> list[User]:
    viewer_dep_ids = {d.id for d in (viewer.departments or [])}
    if not viewer_dep_ids:
        return []
    users = db.query(User).filter(User.company_id == company_id).all()
    result = []
    for u in users:
        u_dep_ids = {d.id for d in (u.departments or [])}
        if viewer_dep_ids.intersection(u_dep_ids):
            result.append(u)
    return result


def _accessible_users(db, company_id: int) -> list[User]:
    viewer = _get_current_user(db)
    if _is_admin(viewer):
        return db.query(User).filter(User.company_id == company_id).all()
    if viewer:
        return _users_in_same_departments(db, viewer, company_id)
    return db.query(User).filter(User.company_id == company_id).all()


def _fmt_deps_for_table(user: User) -> str:
    names = sorted([d.name for d in (user.departments or [])])
    return "—" if not names else "\n".join(f"• {n}" for n in names)


# ==========================
#         MODALS
# ==========================
def _modal(title: str):
    if hasattr(st, "dialog"):
        return st.dialog(title)
    def _cm(func):
        def _wrapped(*args, **kwargs):
            with st.expander(title, expanded=True):
                return func(*args, **kwargs)
        return _wrapped
    return _cm


def _add_employee_modal(db, company_id: int):
    @(_modal("Добавить сотрудника"))
    def _content():
        positions_all = (
            db.query(Position)
            .filter(Position.company_id == company_id)
            .order_by(Position.name.asc())
            .all()
        )
        departments_all = (
            db.query(Department)
            .filter(Department.company_id == company_id)
            .order_by(Department.name.asc())
            .all()
        )

        if not positions_all:
            st.warning("Нет должностей в компании. Сначала создайте должность.")
            st.button("Закрыть", key="close_no_positions", on_click=st.rerun)
            return
        if not departments_all:
            st.warning("Нет подразделений в компании. Сначала создайте подразделение.")
            st.button("Закрыть", key="close_no_deps", on_click=st.rerun)
            return

        with st.form("add_employee_form"):
            # ФИО
            c_nm1, c_nm2 = st.columns(2)
            with c_nm1:
                last_name = st.text_input("Фамилия")
            with c_nm2:
                first_name = st.text_input("Имя")

            # Телефон
            c_ph1, c_ph2 = st.columns([1, 5])
            with c_ph1:
                st.markdown("### +7")
            with c_ph2:
                raw_phone = st.text_input("Телефон (10 цифр)", max_chars=10)

            # Должность
            pos_map = {p.name: p.id for p in positions_all}
            pos_names = list(pos_map.keys())
            position_id = None
            if pos_names:
                selected_pos_name = st.selectbox("Должность", pos_names)
                position_id = pos_map[selected_pos_name]

            st.markdown("---")

            # Подразделения
            dep_map = {d.name: d.id for d in departments_all}
            dep_names = list(dep_map.keys())
            select_all = st.checkbox("Все подразделения", value=False, key="add_emp_all_deps")
            if select_all:
                selected_dep_ids = [d.id for d in departments_all]
                st.caption(f"Будет назначено подразделений: {len(selected_dep_ids)}")
            else:
                selected_dep_names = st.multiselect(
                    "Подразделения (множественный выбор)",
                    options=dep_names,
                    default=[],
                    key="add_emp_dep_multiselect",
                )
                selected_dep_ids = [dep_map[n] for n in selected_dep_names]

            st.markdown("---")

            # Веб‑доступ
            login = st.text_input("Логин (для веб‑версии)", key="add_emp_login")
            password = st.text_input("Пароль", type="password", key="add_emp_password")

            submitted = st.form_submit_button("Добавить")
            if submitted:
                # Валидация
                if not (last_name and first_name and raw_phone and login and password):
                    st.error("Заполните ФИО, телефон, логин и пароль.")
                    return
                if not raw_phone.isdigit() or len(raw_phone) != 10:
                    st.error("Телефон должен содержать ровно 10 цифр.")
                    return
                if not position_id:
                    st.error("Выберите должность.")
                    return
                if not selected_dep_ids:
                    st.error("Выберите хотя бы одно подразделение или поставьте «Все подразделения».")
                    return

                phone = "+7" + raw_phone
                full_name = f"{last_name} {first_name}"

                # Уникальность
                exists = (
                    db.query(User)
                    .filter(User.company_id == company_id, User.phone == phone)
                    .first()
                )
                if exists:
                    st.warning("Сотрудник с таким номером телефона уже существует.")
                    return

                exists_login = db.query(User).filter(User.login == login).first()
                if exists_login:
                    st.warning("Пользователь с таким логином уже существует.")
                    return

                # Создание
                hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

                new_user = User(
                    name=full_name,
                    phone=phone,
                    login=login,
                    hashed_password=hashed,
                    company_id=company_id,
                    position_id=int(position_id),
                )
                db.add(new_user)
                db.commit()
                db.refresh(new_user)

                selected_deps = db.query(Department).filter(Department.id.in_(selected_dep_ids)).all()
                for d in selected_deps:
                    new_user.departments.append(d)
                db.commit()

                st.success(f"Сотрудник «{full_name}» добавлен.")
                st.rerun()
    _content()


# ==========================
#        EDIT (+ DELETE)
# ==========================
def _edit_employee_popover(db, company_id: int):
    with st.popover("✏️ Редактировать сотрудника", use_container_width=True):
        accessible = _accessible_users(db, company_id)
        if not accessible:
            st.info("Нет доступных сотрудников для редактирования.")
            return

        positions_all = (
            db.query(Position)
            .filter(Position.company_id == company_id)
            .order_by(Position.name.asc())
            .all()
        )
        departments_all = (
            db.query(Department)
            .filter(Department.company_id == company_id)
            .order_by(Department.name.asc())
            .all()
        )

        labels = [f"{u.name} · {u.phone or 'без телефона'}" for u in accessible]
        id_by_label = {labels[i]: accessible[i].id for i in range(len(accessible))}
        selected_label = st.selectbox("Выберите сотрудника", labels, index=0)
        user_id = id_by_label.get(selected_label)

        if not user_id:
            st.warning("Сотрудник не выбран.")
            return

        u = db.query(User).filter(User.company_id == company_id, User.id == user_id).first()
        if not u:
            st.error("Сотрудник не найден.")
            return

        with st.form(f"edit_user_form_{u.id}"):
            # ФИО
            parts = (u.name or "").split(" ", 1)
            cur_last = parts[0] if parts and parts[0] else ""
            cur_first = parts[1] if len(parts) > 1 else ""
            c_nm1, c_nm2 = st.columns(2)
            with c_nm1:
                last_name = st.text_input("Фамилия", value=cur_last)
            with c_nm2:
                first_name = st.text_input("Имя", value=cur_first)

            # Телефон
            phone_wo_code = (u.phone or "").replace("+7", "")
            c_ph1, c_ph2 = st.columns([1, 5])
            with c_ph1:
                st.markdown("### +7")
            with c_ph2:
                raw_phone = st.text_input("Телефон (10 цифр)", value=phone_wo_code, max_chars=10)

            # Должность
            pos_map = {p.name: p.id for p in positions_all}
            pos_names = list(pos_map.keys())
            current_pos_name = u.position.name if u.position else None
            default_pos_index = pos_names.index(current_pos_name) if current_pos_name in pos_names else 0
            selected_pos_name = st.selectbox("Должность", pos_names, index=default_pos_index if pos_names else 0)
            position_id = pos_map.get(selected_pos_name)

            st.markdown("---")

            # Подразделения
            dep_map = {d.name: d.id for d in departments_all}
            dep_names = list(dep_map.keys())
            current_dep_ids = {d.id for d in (u.departments or [])}
            select_all = st.checkbox(
                "Все подразделения",
                value=(len(current_dep_ids) == len(departments_all)),
                key=f"edit_emp_all_deps_{u.id}"
            )
            if select_all:
                selected_dep_ids = [d.id for d in departments_all]
                st.caption(f"Будет назначено подразделений: {len(selected_dep_ids)}")
                selected_dep_names = dep_names
            else:
                default_dep_names = [d.name for d in departments_all if d.id in current_dep_ids]
                selected_dep_names = st.multiselect(
                    "Подразделения (множественный выбор)",
                    options=dep_names,
                    default=default_dep_names,
                    key=f"edit_emp_dep_multiselect_{u.id}",
                )
                selected_dep_ids = [dep_map[n] for n in selected_dep_names]

            st.markdown("---")

            # Веб‑доступ
            login = st.text_input("Логин (для веб‑версии)", value=u.login or "", key=f"edit_login_{u.id}")
            new_password = st.text_input("Новый пароль (необязательно)", type="password", key=f"edit_newpass_{u.id}")

            col_save, col_del = st.columns(2)
            with col_save:
                submitted = st.form_submit_button("Сохранить изменения")
            with col_del:
                if st.form_submit_button("🗑️ Удалить сотрудника", type="secondary"):
                    st.session_state["__del_user_pending"] = u.id  # запомним на подтверждение

        # --- обработка сохранения
        if submitted:
            if not (last_name and first_name and raw_phone and login):
                st.error("Заполните ФИО, телефон и логин.")
                return
            if not raw_phone.isdigit() or len(raw_phone) != 10:
                st.error("Телефон должен содержать ровно 10 цифр.")
                return
            if not position_id:
                st.error("Выберите должность.")
                return
            if not selected_dep_ids:
                st.error("Выберите хотя бы одно подразделение или поставьте «Все подразделения».")
                return

            phone = "+7" + raw_phone
            full_name = f"{last_name} {first_name}"

            # телефон — уникальность (кроме себя)
            exists_phone = (
                db.query(User)
                .filter(User.company_id == company_id, User.phone == phone, User.id != u.id)
                .first()
            )
            if exists_phone:
                st.warning("Другой сотрудник уже использует этот номер телефона.")
                return

            # логин — уникальность (кроме себя)
            exists_login = (
                db.query(User)
                .filter(User.login == login, User.id != u.id)
                .first()
            )
            if exists_login:
                st.warning("Этот логин уже занят другим пользователем.")
                return

            # сохранение
            u.name = full_name
            u.phone = phone
            u.position_id = int(position_id)
            u.login = login

            if new_password:
                u.hashed_password = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()

            new_deps = db.query(Department).filter(Department.id.in_(selected_dep_ids)).all()
            u.departments.clear()
            for d in new_deps:
                u.departments.append(d)

            db.commit()
            st.success("Изменения сохранены.")
            st.rerun()

        # --- подтверждение удаления (вне формы; двухкликовое подтверждение)
        pending_id = st.session_state.get("__del_user_pending")
        if pending_id == u.id:
            st.warning("Удаление сотрудника необратимо. Также будут удалены все его ответы в чек‑листах.")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("✅ Да, удалить навсегда", key=f"confirm_del_user_{u.id}"):
                    try:
                        ans_ids = [a_id for (a_id,) in db.query(ChecklistAnswer.id)
                                   .filter(ChecklistAnswer.user_id == u.id).all()]
                        if ans_ids:
                            db.query(ChecklistQuestionAnswer)\
                                .filter(ChecklistQuestionAnswer.answer_id.in_(ans_ids))\
                                .delete(synchronize_session=False)
                            db.query(ChecklistAnswer)\
                                .filter(ChecklistAnswer.id.in_(ans_ids))\
                                .delete(synchronize_session=False)
                        db.delete(u)
                        db.commit()
                        st.success("Сотрудник и его ответы удалены.")
                    except Exception as e:
                        db.rollback()
                        st.error(f"Ошибка при удалении: {e}")
                    finally:
                        st.session_state.pop("__del_user_pending", None)
                        st.rerun()
            with c2:
                if st.button("Отмена", key=f"cancel_del_user_{u.id}"):
                    st.session_state.pop("__del_user_pending", None)
                    st.rerun()


# ==========================
#        TAB RENDER
# ==========================
def employees_user_tab(company_id: int):
    st.markdown("### Сотрудники")

    db = SessionLocal()
    users = _accessible_users(db, company_id)

    if not users:
        st.info("Нет сотрудников для отображения по вашим правам доступа.")
        df = pd.DataFrame(columns=["ФИО", "Телефон", "Подразделения", "Должность", "Уровень доступа"])
    else:
        rows = []
        for u in users:
            dep_names = _fmt_deps_for_table(u)
            pos_name = u.position.name if u.position else "Не указана"
            role_name = (u.position.role.name if (u.position and u.position.role) else "—")
            rows.append(
                {
                    "ФИО": u.name,
                    "Телефон": u.phone or "",
                    "Подразделения": dep_names,
                    "Должность": pos_name,
                    "Уровень доступа": role_name,
                }
            )
        df = pd.DataFrame(rows)

    df.index = [''] * len(df)  # скрыть нумерацию строк слева
    st.table(df)

    c1, c2 = st.columns(2)
    with c1:
        if st.button("➕ Добавить сотрудника", type="primary"):
            _add_employee_modal(db, company_id)
    with c2:
        _edit_employee_popover(db, company_id)

    db.close()

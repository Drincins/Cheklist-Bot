# checklist/admcompany/employees_position.py
# Вкладка «Должности и доступы»: список, добавление, редактирование,
# и УДАЛЕНИЕ должности прямо в форме редактирования (двухкликовое подтверждение через session_state).

from __future__ import annotations

import streamlit as st
import pandas as pd
from typing import Optional

from checklist.db.db import SessionLocal
from checklist.db.models import Role, Position, Checklist, User


# ---------------------------
#   ТЕКУЩИЙ ПОЛЬЗОВАТЕЛЬ
# ---------------------------
def _get_current_user(db) -> Optional[User]:
    uid = st.session_state.get("user_id")
    if uid:
        return db.query(User).get(int(uid))
    tg_id = st.session_state.get("telegram_id")
    if tg_id:
        return db.query(User).filter(User.telegram_id == int(tg_id)).first()
    return None


def _viewer_role(db) -> Optional[Role]:
    u = _get_current_user(db)
    return u.position.role if (u and u.position and u.position.role) else None


# ---------------------------
#   ИЕРАРХИЯ РОЛЕЙ (опц.)
# ---------------------------
def _role_level(role: Optional[Role]) -> Optional[int]:
    if not role:
        return None
    lvl = getattr(role, "level", None)
    try:
        return int(lvl) if lvl is not None else None
    except Exception:
        return None


def _allowed_roles_for_viewer(roles_all: list[Role], viewer: Optional[Role]) -> list[Role]:
    if not viewer:
        return []
    v_level = _role_level(viewer)
    if v_level is not None:
        out: list[Role] = []
        for r in roles_all:
            rl = _role_level(r)
            if rl is None:
                continue
            if rl <= v_level:
                out.append(r)
        return out
    return [r for r in roles_all if r.id == viewer.id]


def _is_position_above_viewer(pos_role: Optional[Role], viewer: Optional[Role]) -> bool:
    if not pos_role or not viewer:
        return False
    pr, vr = _role_level(pos_role), _role_level(viewer)
    if pr is not None and vr is not None:
        return pr > vr
    return pos_role.id != viewer.id


# ---------------------------
#       ОТОБРАЖЕНИЕ
# ---------------------------
def _render_positions_table(db, company_id: int):
    positions = db.query(Position).filter(Position.company_id == company_id).all()
    if not positions:
        st.info("Должностей пока нет.")
        return

    rows = []
    for p in positions:
        role_name = p.role.name if p.role else "—"
        users_count = (
            db.query(User)
            .filter(User.company_id == company_id, User.position_id == p.id)
            .count()
        )
        rows.append({
            "Должность": p.name,
            "Роль (уровень)": role_name,
            "Пользователей": users_count,
        })

    df = pd.DataFrame(rows, columns=["Должность", "Роль (уровень)", "Пользователей"])
    df.index = [''] * len(df)
    st.table(df)


# ---------------------------
#         ДОБАВЛЕНИЕ
# ---------------------------
def _add_position_modal(db, company_id: int):
    if hasattr(st, "dialog"):
        @st.dialog("Добавить должность")
        def _dlg():
            _add_or_edit_form(db, company_id, is_edit=False)
        _dlg()
    else:
        with st.expander("Добавить должность", expanded=True):
            _add_or_edit_form(db, company_id, is_edit=False)


# ---------------------------
#         РЕДАКТИРОВАНИЕ (+ DELETE)
# ---------------------------
def _edit_position_popover(db, company_id: int):
    with st.popover("✏️ Редактировать должность", use_container_width=True):
        positions = (
            db.query(Position)
            .filter(Position.company_id == company_id)
            .order_by(Position.name.asc())
            .all()
        )
        if not positions:
            st.info("Нет должностей для редактирования.")
            return

        pos_labels = [f"{p.name} · роль: {p.role.name if p.role else '—'}" for p in positions]
        by_label = {pos_labels[i]: positions[i].id for i in range(len(positions))}
        choice = st.selectbox("Выберите должность", pos_labels, index=0)
        pos_id = by_label.get(choice)
        if not pos_id:
            st.warning("Должность не выбрана.")
            return

        position = db.query(Position).get(pos_id)
        _add_or_edit_form(db, company_id, is_edit=True, position=position)


# ---------------------------
#    ФОРМА ADD / EDIT (+DELETE)
# ---------------------------
def _add_or_edit_form(db, company_id: int, *, is_edit: bool, position: Optional[Position] = None):
    roles_all = db.query(Role).order_by(Role.name.asc()).all()
    checklists_all = (
        db.query(Checklist)
        .filter(Checklist.company_id == company_id)
        .order_by(Checklist.name.asc())
        .all()
    )

    viewer = _viewer_role(db)
    allowed_roles = _allowed_roles_for_viewer(roles_all, viewer)

    if not viewer:
        st.warning("Не удалось определить роль текущего пользователя.")
        return
    if not allowed_roles:
        st.warning("У вас нет прав создавать/редактировать должности.")
        return

    with st.form(f"{'edit' if is_edit else 'add'}_position_form"):
        name = st.text_input(
            "Название должности",
            value=(position.name if (is_edit and position) else "")
        )

        role_names = [r.name for r in allowed_roles]
        default_role_idx = 0
        if is_edit and position and position.role:
            try:
                default_role_idx = role_names.index(position.role.name)
            except ValueError:
                default_role_idx = 0
        role_name_selected = st.selectbox("Права доступа (роль)", role_names, index=default_role_idx)
        role_id_selected = next(r.id for r in allowed_roles if r.name == role_name_selected)

        chk_map = {c.name: c.id for c in checklists_all}
        default_chk_names = [c.name for c in (position.checklists or [])] if (is_edit and position) else []
        chk_selected_names = st.multiselect(
            "Чек-листы, доступные по должности",
            options=list(chk_map.keys()),
            default=default_chk_names
        )
        chk_selected_ids = [chk_map[n] for n in chk_selected_names]

        col_save, col_del = st.columns(2)
        with col_save:
            submit = st.form_submit_button("Сохранить" if is_edit else "Добавить")
        with col_del:
            if is_edit and st.form_submit_button("🗑️ Удалить должность", type="secondary"):
                st.session_state["__del_pos_pending"] = position.id  # запомним на подтверждение

    # --- добавление
    if not is_edit and submit:
        if not name.strip():
            st.error("Введите название должности.")
            return
        exists = (
            db.query(Position)
            .filter(Position.company_id == company_id, Position.name == name.strip())
            .first()
        )
        if exists:
            st.warning("Такая должность уже существует.")
            return
        new_pos = Position(name=name.strip(), company_id=company_id, role_id=role_id_selected)
        db.add(new_pos)
        db.commit()
        db.refresh(new_pos)
        if chk_selected_ids:
            chks = db.query(Checklist).filter(Checklist.id.in_(chk_selected_ids)).all()
            new_pos.checklists = chks
            db.commit()
        st.success("Должность добавлена.")
        st.rerun()
        return

    # --- редактирование
    if is_edit and position:
        if submit:
            if not name.strip():
                st.error("Введите название должности.")
                return
            new_role = next((r for r in allowed_roles if r.id == role_id_selected), None)
            if not new_role:
                st.error("Выбранная роль недоступна.")
                return
            if _is_position_above_viewer(new_role, viewer):
                st.error("Нельзя назначить роль выше ваших прав.")
                return
            position.name = name.strip()
            position.role_id = new_role.id
            chks = db.query(Checklist).filter(Checklist.id.in_(chk_selected_ids)).all()
            position.checklists = chks
            db.commit()
            st.success("Изменения сохранены.")
            st.rerun()
            return

        # --- подтверждение удаления (вне формы; двухкликовое подтверждение)
        if st.session_state.get("__del_pos_pending") == position.id:
            users_count = db.query(User).filter(
                User.company_id == company_id,
                User.position_id == position.id
            ).count()
            if users_count > 0:
                st.error(f"Нельзя удалить должность — к ней привязано пользователей: {users_count}.")
                if st.button("Понятно", key=f"del_pos_blocked_ok_{position.id}"):
                    st.session_state.pop("__del_pos_pending", None)
                    st.rerun()
            else:
                st.warning("Удаление должности необратимо. Связи с чек‑листами будут удалены.")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("✅ Да, удалить должность навсегда", key=f"confirm_del_pos_{position.id}"):
                        try:
                            # Явно очистим M2M связи на всякий случай
                            position.checklists = []
                            db.commit()
                            db.delete(position)
                            db.commit()
                            st.success("Должность удалена.")
                        except Exception as e:
                            db.rollback()
                            st.error(f"Ошибка при удалении должности: {e}")
                        finally:
                            st.session_state.pop("__del_pos_pending", None)
                            st.rerun()
                with c2:
                    if st.button("Отмена", key=f"cancel_del_pos_{position.id}"):
                        st.session_state.pop("__del_pos_pending", None)
                        st.rerun()


# ---------------------------
#        TAB RENDER
# ---------------------------
def employees_position_tab(company_id: int):
    st.markdown("### Должности и доступы")

    db = SessionLocal()
    try:
        _render_positions_table(db, company_id)

        c1, c2 = st.columns(2)
        with c1:
            if st.button("➕ Добавить должность", type="primary"):
                _add_position_modal(db, company_id)
        with c2:
            _edit_position_popover(db, company_id)
    finally:
        db.close()

# handlers/fsm.py

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from ..states import Form
from ..bot_logic import (
    find_user_by_name_phone_company,
    get_checklists_for_user,
    get_completed_checklists_for_user,   # пусть останется, вдруг используется ещё где-то
    get_completed_answers_paginated,     # НОВОЕ — используется ниже
    get_answer_report_data,              # НОВОЕ — используется ниже
)
from ..keyboards.inline import get_identity_confirmation_keyboard, get_checklists_keyboard
from ..keyboards.reply import authorized_keyboard
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

router = Router()


# 🚀 Нажал "Начать"
@router.callback_query(F.data == "start_checklist")
async def ask_name(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите вашу *Фамилию и Имя*:")
    await state.set_state(Form.entering_name)
    await callback.answer()


# ✍️ Вводит имя
@router.message(Form.entering_name)
async def ask_phone(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer("Введите ваш номер телефона:")
    await state.set_state(Form.entering_phone)


# ☎️ Вводит телефон → проверка
@router.message(Form.entering_phone)
async def confirm_user(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text.strip())
    data = await state.get_data()

    user = find_user_by_name_phone_company(
        data.get("name", "").strip(),
        data.get("phone", "").strip(),
        company_name=None,
    )

    if user:
        await state.update_data(user_id=user["id"], user=user)
        await state.set_state(Form.show_checklists)

        await message.answer(
            "🔎 Проверьте данные:\n\n"
            f"*Фамилия и Имя:* {user['name']}\n"
            f"*Телефон:* {user['phone']}\n"
            f"*Компания:* {user.get('company_name', '—')}\n"
            f"*Должность:* {user.get('position', '—')}",
            reply_markup=get_identity_confirmation_keyboard(),
            parse_mode="Markdown",
        )
    else:
        await message.answer(
            "❌ Пользователь не найден.\n"
            "Проверьте написание имени и последние 10 цифр телефона и попробуйте снова."
        )
        await state.set_state(Form.entering_name)


# ✅ Подтверждение личности
@router.callback_query(F.data == "confirm_identity", Form.show_checklists)
async def identity_approved(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id")

    await callback.message.answer(
        "✅ Авторизация прошла успешно. Главное меню появилось снизу 👇",
        reply_markup=authorized_keyboard,
    )

    # Сразу показываем чек-листы (если нужно — раскомментируйте)
    # if user_id:
    #     checklists = get_checklists_for_user(user_id)
    #     if checklists:
    #         await callback.message.answer(
    #             "📋 Доступные чек-листы:",
    #             reply_markup=get_checklists_keyboard(checklists),
    #         )
    #     else:
    #         await callback.message.answer(
    #             "🙁 У вас пока нет доступных чек-листов.\n"
    #             "Если это ошибка — проверьте назначение чек-листов на вашу должность."
    #         )

    await state.set_state(Form.show_checklists)
    await callback.answer()


# ❌ Отклонение
@router.callback_query(F.data == "reject_identity", Form.show_checklists)
async def identity_rejected(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Попробуем снова. Введите вашу *Фамилию и Имя*:")
    await state.set_state(Form.entering_name)
    await callback.answer()


# ✅ Обработка кнопки "Доступные чек-листы"
@router.message((F.text == "✅ Доступные чек-листы") | (F.text == "✅ доступные чек-листы"))
async def show_available_checklists(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id")

    if not user_id:
        await message.answer("⚠️ Сначала нужно авторизоваться через /start")
        return

    checklists = get_checklists_for_user(user_id)
    if checklists:
        await message.answer(
            "📋 Доступные чек-листы:",
            reply_markup=get_checklists_keyboard(checklists),
        )
        await state.set_state(Form.show_checklists)
    else:
        await message.answer("🙁 У вас пока нет доступных чек-листов.")


# ──────────────────────────────────────────────────────────────────────────────
# 📋 ПРОЙДЕННЫЕ ЧЕК-ЛИСТЫ — НОВЫЙ БЛОК (вместо старого show_completed_checklists)
# ──────────────────────────────────────────────────────────────────────────────

PAGE_LIMIT = 8  # показываем по 8 на страницу

def _build_completed_list_text(items, offset: int) -> str:
    if not items:
        return "Пока нет пройденных чек-листов."
    lines = ["Ваши последние чек-листы:\n"]
    for i, it in enumerate(items, start=1):
        idx = offset + i  # глобальная нумерация: 1..N
        dt = it["submitted_at"].strftime("%d.%m.%Y %H:%M")
        lines.append(f"{idx}. {it['checklist_name']} — {dt}")
    return "\n".join(lines)

def _build_completed_list_kb(items, offset: int, total: int) -> InlineKeyboardMarkup:
    kb_rows = []

    # Кнопки с номерами текущих карточек (по 4 в ряд)
    number_buttons = []
    for i, it in enumerate(items, start=1):
        idx = offset + i
        number_buttons.append(
            InlineKeyboardButton(
                text=str(idx),
                callback_data=f"completed_view:{it['answer_id']}:{offset}"
            )
        )
        if len(number_buttons) == 4:
            kb_rows.append(number_buttons)
            number_buttons = []
    if number_buttons:
        kb_rows.append(number_buttons)

    # Навигация страниц (если всего больше лимита)
    if total > PAGE_LIMIT:
        nav_row = []
        if offset > 0:
            nav_row.append(
                InlineKeyboardButton(
                    text="⟵ Назад",
                    callback_data=f"completed_page:{max(0, offset - PAGE_LIMIT)}"
                )
            )
        if offset + PAGE_LIMIT < total:
            nav_row.append(
                InlineKeyboardButton(
                    text="Вперёд ⟶",
                    callback_data=f"completed_page:{offset + PAGE_LIMIT}"
                )
            )
        if nav_row:
            kb_rows.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=kb_rows)

@router.message((F.text == "📋 Пройденные чек-листы") | (F.text == "📋 пройденные чек-листы"))
async def handle_completed_list(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id")

    if not user_id:
        await message.answer("⚠️ Сначала нужно авторизоваться.")
        return

    offset = 0
    items, total = get_completed_answers_paginated(
        user_id=user_id,
        offset=offset,
        limit=PAGE_LIMIT
    )

    if total == 0:
        await message.answer("🕵️‍♂️ Вы ещё не проходили ни одного чек-листа.")
        return

    text = _build_completed_list_text(items, offset)
    kb = _build_completed_list_kb(items, offset, total)
    await message.answer(text, reply_markup=kb)

@router.callback_query(F.data.startswith("completed_page:"))
async def handle_completed_page(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id")

    if not user_id:
        await callback.answer("Не авторизованы", show_alert=True)
        return

    try:
        offset = int(callback.data.split(":")[1])
    except Exception:
        offset = 0

    items, total = get_completed_answers_paginated(
        user_id=user_id,
        offset=offset,
        limit=PAGE_LIMIT
    )
    text = _build_completed_list_text(items, offset)
    kb = _build_completed_list_kb(items, offset, total)

    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("completed_view:"))
async def handle_completed_view(callback: types.CallbackQuery):
    # формат: completed_view:<answer_id>:<offset>
    parts = callback.data.split(":")
    answer_id = int(parts[1])
    offset = int(parts[2]) if len(parts) > 2 else 0

    data = get_answer_report_data(answer_id)
    if not data:
        await callback.answer("Не удалось получить данные отчёта", show_alert=True)
        return

    res_line = f"\nРезультат: {data['result']}" if data.get("result") else ""
    text = (
        f"📋 <b>{data['checklist_name']}</b>\n"
        f"Дата: {data['date']}\n"
        f"Время: {data['time']}\n"
        f"Подразделение: {data['department']}{res_line}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📄 PDF",   callback_data=f"completed_pdf:{answer_id}:{offset}"),
            InlineKeyboardButton(text="📊 Excel", callback_data=f"completed_excel:{answer_id}:{offset}"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад к списку", callback_data=f"completed_page:{offset}")
        ]
    ])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("completed_pdf:"))
async def handle_completed_pdf(callback: types.CallbackQuery):
    # Пока просто сообщение и возможность вернуться назад
    parts = callback.data.split(":")
    answer_id = int(parts[1])
    offset = int(parts[2]) if len(parts) > 2 else 0

    await callback.answer()  # закрыть "часики"
    await callback.message.answer("📄 Отчёт сформирован! (демо)")
    # остаёмся на текущем экране; возврат — кнопкой «⬅️ Назад к списку»

@router.callback_query(F.data.startswith("completed_excel:"))
async def handle_completed_excel(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    answer_id = int(parts[1])
    offset = int(parts[2]) if len(parts) > 2 else 0

    await callback.answer()
    await callback.message.answer("📊 Отчёт сформирован! (демо)")
    # остаёмся на текущем экране; возврат — кнопкой «⬅️ Назад к списку»


# ──────────────────────────────────────────────────────────────────────────────

@router.message((F.text == "ℹ️ Обо мне") | (F.text == "ℹ️ обо мне"))
async def show_user_info(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user = data.get("user")

    if not user:
        await message.answer("⚠️ Вы не авторизованы.")
        return

    text = (
        f"👤 *Информация о вас:*\n\n"
        f"*Фамилия и Имя:* {user['name']}\n"
        f"*Телефон:* {user['phone']}\n"
        f"*Компания:* {user.get('company_name', '—')}\n"
        f"*Должность:* {user.get('position', '—')}"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📋 Меню", callback_data="back_to_menu")]]
    )

    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard)


@router.callback_query(F.data == "back_to_menu")
async def return_to_main_menu(callback: types.CallbackQuery):
    await callback.message.answer("📋 Главное меню:", reply_markup=authorized_keyboard)
    await callback.answer()


@router.message((F.text == "🚪 Выйти") | (F.text == "🚪 выйти"))
async def handle_logout(message: types.Message, state: FSMContext):
    from keyboards.inline import get_start_keyboard

    await state.clear()
    await message.answer("🚪 Вы вышли из системы.")

    await message.answer(
        "👋 Добро пожаловать!\n\nНажмите *🚀 Начать*, чтобы пройти чек-лист.\n"
        "Или *📖 Инструкция*, чтобы узнать подробнее.",
        reply_markup=get_start_keyboard(),
        parse_mode="Markdown",
    )

# handlers/fsm.py

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from states import Form
from bot_logic import find_user_by_name_phone_company, get_checklists_for_user
from keyboards.inline import get_identity_confirmation_keyboard, get_checklists_keyboard
from keyboards.reply import authorized_keyboard
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

    user = find_user_by_name_phone_company(data["name"], data["phone"], company_name=None)
    if user:
        await state.update_data(user_id=user["id"], user=user)
        await state.set_state(Form.show_checklists)

        await message.answer(
            f"🔎 Проверьте данные:\n\n"
            f"*Фамилия и Имя:* {user['name']}\n"
            f"*Телефон:* {user['phone']}\n"
            f"*Компания:* {user.get('company_name', '—')}\n"
            f"*Должность:* {user['position']}",
            reply_markup=get_identity_confirmation_keyboard(),
            parse_mode="Markdown"
        )
    else:
        await message.answer("❌ Пользователь не найден. Проверьте данные и попробуйте снова.")
        await state.set_state(Form.entering_name)

# ✅ Подтверждение личности
@router.callback_query(F.data == "confirm_identity", Form.show_checklists)
async def identity_approved(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "✅ Авторизация прошла успешно. Главное меню появилось снизу 👇",
        reply_markup=authorized_keyboard
    )
    await callback.answer()

# ❌ Отклонение
@router.callback_query(F.data == "reject_identity", Form.show_checklists)
async def identity_rejected(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Попробуем снова. Введите вашу *Фамилию и Имя*:")
    await state.set_state(Form.entering_name)
    await callback.answer()

# ✅ Обработка кнопки "Доступные чек-листы"
@router.message(F.text.lower() == "✅ доступные чек-листы")
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
            reply_markup=get_checklists_keyboard(checklists)
        )
        await state.set_state(Form.show_checklists)
    else:
        await message.answer("🙁 У вас пока нет доступных чек-листов.")

@router.message(F.text.lower() == "📋 пройденные чек-листы")
async def show_completed_checklists(message: types.Message, state: FSMContext):
    from bot_logic import get_completed_checklists_for_user
    data = await state.get_data()
    user_id = data.get("user_id")

    if not user_id:
        await message.answer("⚠️ Сначала нужно авторизоваться.")
        return

    checklists = get_completed_checklists_for_user(user_id)

    if not checklists:
        await message.answer("🕵️‍♂️ Вы ещё не проходили ни одного чек-листа.")
        return

    text = "📋 Пройденные чек-листы:\n\n"
    for item in checklists:
        text += f"• {item['name']} — {item['completed_at'].strftime('%d.%m.%Y %H:%M')}\n"

    await message.answer(text)

@router.message(F.text.lower() == "ℹ️ обо мне")
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
        f"*Должность:* {user['position']}"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Меню", callback_data="back_to_menu")]
    ])

    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard)

@router.callback_query(F.data == "back_to_menu")
async def return_to_main_menu(callback: types.CallbackQuery):
    await callback.message.answer("📋 Главное меню:", reply_markup=authorized_keyboard)
    await callback.answer()

@router.message(F.text.lower() == "🚪 выйти")
async def handle_logout(message: types.Message, state: FSMContext):
    from keyboards.inline import get_start_keyboard

    await state.clear()
    await message.answer("🚪 Вы вышли из системы.")

    await message.answer(
        "👋 Добро пожаловать!\n\nНажмите *🚀 Начать*, чтобы пройти чек-лист.\nИли *📖 Инструкция*, чтобы узнать подробнее.",
        reply_markup=get_start_keyboard(),
        parse_mode="Markdown"
    )

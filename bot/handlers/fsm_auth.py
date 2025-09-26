# handlers/fsm_auth.py — авторизация, профиль, выход
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from ..states import Form
from ..services.auth import AuthService                      # ← сервис-слой вместо прямых вызовов bot_logic
from ..keyboards.inline import (
    get_identity_confirmation_keyboard,
    get_checklists_keyboard,
)
from ..keyboards.reply import authorized_keyboard

router = Router()


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

    name = data.get("name", "").strip()
    phone = data.get("phone", "").strip()

    # company_id у тебя сейчас не вводится — передаём None (совместимо с текущей логикой)
    svc = AuthService()
    user = svc.find_user(name=name, phone=phone, company_id=None)

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

    # При желании можно сразу показать чек-листы:
    # if user_id:
    #     svc = AuthService()
    #     checklists = svc.get_user_checklists(user_id)
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


# ℹ️ Профиль
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
    # исправленный относительный импорт!
    from ..keyboards.inline import get_start_keyboard

    await state.clear()
    await message.answer("🚪 Вы вышли из системы.")

    await message.answer(
        "👋 Добро пожаловать!\n\nНажмите *🚀 Начать*, чтобы пройти чек-лист.\n"
        "Или *📖 Инструкция*, чтобы узнать подробнее.",
        reply_markup=get_start_keyboard(),
        parse_mode="Markdown",
    )

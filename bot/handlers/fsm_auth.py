# handlers/fsm_auth.py — авторизация, профиль, выход
import asyncio
import html

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
auth_service = AuthService()


def _escape(text: str | None) -> str:
    return html.escape(text or "")


@router.callback_query(F.data == "start_checklist")
async def ask_login(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ваш логин:")
    await state.set_state(Form.entering_login)
    await callback.answer()


# ✍️ Вводит логин
@router.message(Form.entering_login)
async def ask_password(message: types.Message, state: FSMContext):
    await state.update_data(login=message.text.strip())
    await message.answer("Введите ваш пароль:")
    await state.set_state(Form.entering_password)


# 🔐 Вводит пароль → проверка
@router.message(Form.entering_password)
async def confirm_user(message: types.Message, state: FSMContext):
    await state.update_data(password=message.text.strip())
    data = await state.get_data()

    login = data.get("login", "").strip()
    password = data.get("password", "")

    user = await asyncio.to_thread(auth_service.authenticate, login, password)

    if user:
        await state.update_data(user_id=user["id"], user=user)
        await state.set_state(Form.awaiting_confirmation)

        # не храним пароль в состоянии
        await state.update_data(password=None)

        details = (
            "🔎 Проверьте данные:\n\n"
            f"<b>Сотрудник:</b> {_escape(user.get('name'))}\n"
            f"<b>Логин:</b> {_escape(login)}\n"
            f"<b>Компания:</b> {_escape(user.get('company_name', '—'))}\n"
            f"<b>Должность:</b> {_escape(user.get('position', '—'))}"
        )
        await message.answer(
            details,
            reply_markup=get_identity_confirmation_keyboard(),
            parse_mode="HTML",
        )
    else:
        await message.answer(
            "❌ Неверный логин или пароль. Попробуйте снова."
        )
        await state.update_data(password=None)
        await state.set_state(Form.entering_login)


# ✅ Подтверждение личности
@router.callback_query(F.data == "confirm_identity", Form.awaiting_confirmation)
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
@router.callback_query(F.data == "reject_identity", Form.awaiting_confirmation)
async def identity_rejected(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Попробуем снова. Введите ваш логин:")
    await state.set_state(Form.entering_login)
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
        "👤 <b>Информация о вас:</b>\n\n"
        f"<b>Фамилия и Имя:</b> {_escape(user.get('name'))}\n"
        f"<b>Телефон:</b> {_escape(user.get('phone'))}\n"
        f"<b>Компания:</b> {_escape(user.get('company_name', '—'))}\n"
        f"<b>Должность:</b> {_escape(user.get('position', '—'))}"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📋 Меню", callback_data="back_to_menu")]]
    )

    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


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
        "👋 Добро пожаловать!\n\nНажмите <b>🚀 Начать</b>, чтобы пройти чек-лист.\n"
        "Или <b>📖 Инструкция</b>, чтобы узнать подробнее.",
        reply_markup=get_start_keyboard(),
        parse_mode="HTML",
    )

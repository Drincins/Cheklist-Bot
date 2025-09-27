# handlers/start.py

import asyncio

from aiogram import Router, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from ..keyboards.inline import get_start_keyboard, get_checklists_keyboard
from ..keyboards.reply import authorized_keyboard
from ..services.auth import AuthService

router = Router()  # ✅ ОБЯЗАТЕЛЬНО добавить

auth_service = AuthService()


async def send_main_menu(message: types.Message):
    await message.answer(
        "👋 Добро пожаловать в основное меню!",
        reply_markup=authorized_keyboard
    )

@router.message(CommandStart())
async def handle_start(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id")

    if user_id:
        checklists = await asyncio.to_thread(auth_service.get_user_checklists, user_id)
        await send_main_menu(message)
        if checklists:
            await message.answer("Выберите чек-лист:", reply_markup=get_checklists_keyboard(checklists))
        else:
            await message.answer("У вас пока нет доступных чек-листов.")
        return

    # До авторизации — только inline-кнопки
    await message.answer(
        "Привет! Это сервис для прохождения чек-листов. Выбери, что хочешь сделать:",
        reply_markup=get_start_keyboard()
    )


@router.message(F.text == "🏠 Домой")
async def handle_home(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id")
    if not user_id:
        await message.answer("⚠️ Сначала нужно авторизоваться через /start", reply_markup=get_start_keyboard())
        return

    await send_main_menu(message)

# handlers/start.py

from aiogram import Router, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from ..keyboards.inline import get_start_keyboard, get_checklists_keyboard
from ..keyboards.reply import authorized_keyboard
from ..bot_logic import get_checklists_for_user

router = Router()  # ✅ ОБЯЗАТЕЛЬНО добавить

@router.message(CommandStart())
async def handle_start(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id")

    if user_id:
        checklists = get_checklists_for_user(user_id)
        await message.answer(
            "👋 Снова привет! Вот доступные чек-листы:",
            reply_markup=authorized_keyboard
        )
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

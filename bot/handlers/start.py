# handlers/start.py

from aiogram import Router, types
from aiogram.filters import CommandStart
from keyboards.inline import get_start_keyboard  # Импортируем функцию клавиатуры

router = Router()

@router.message(CommandStart())
async def handle_start(message: types.Message):
    await message.answer(
        "Привет! Это сервис для прохождения чек-листов. Выбери, что хочешь сделать:",
        reply_markup=get_start_keyboard()
    )

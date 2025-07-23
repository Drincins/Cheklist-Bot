# handlers/fallback.py

from aiogram import Router, types
from aiogram.filters import Command

router = Router()

@router.message()
async def fallback_message(message: types.Message):
    if not message.text.startswith("/"):
        await message.answer(
            "Я тебя понял, но сейчас лучше нажимай на кнопки ниже или начни с команды /start 😉"
        )

@router.callback_query()
async def fallback_callback(callback: types.CallbackQuery):
    await callback.answer("Эта кнопка пока ни за что не отвечает 🤷‍♂️", show_alert=True)

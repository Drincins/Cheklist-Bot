# bot/keyboards/reply.py

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# Меню после авторизации (ReplyKeyboard)
authorized_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ Доступные чек-листы")],
        [KeyboardButton(text="📋 Пройденные чек-листы")],
        [KeyboardButton(text="ℹ️ Обо мне")],
        [KeyboardButton(text="🏠 Домой"), KeyboardButton(text="🚪 Выйти")]
    ],
    resize_keyboard=True,
    input_field_placeholder="Выберите действие"
)

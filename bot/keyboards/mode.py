# bot/keyboards/mode.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def build_mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧭 Заполнять пошагово", callback_data="mode:step")],
        [InlineKeyboardButton(text="📜 Показать весь чек-лист", callback_data="mode:preview")],
    ])

def build_start_after_preview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Приступить к заполнению", callback_data="mode:step")],
    ])

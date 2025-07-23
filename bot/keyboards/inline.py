# keyboards/inline.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_start_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🚀 Начать", callback_data="start_checklist"),
                InlineKeyboardButton(text="ℹ️ Инструкция", callback_data="instruction")
            ]
        ]
    )

def get_companies_keyboard(companies: list[str]):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=company, callback_data=f"company:{company}")]
            for company in companies
        ]
    )

def get_yes_no_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data="answer:yes"),
                InlineKeyboardButton(text="❌ Нет", callback_data="answer:no")
            ]
        ]
    )

def get_scale_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=str(i), callback_data=f"answer:{i}")]
            for i in range(1, 6)
        ]
    )

def get_checklists_keyboard(checklists: list[dict]):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=cl["name"], callback_data=f"checklist:{cl['id']}")]
            for cl in checklists
        ]
    )
def get_identity_confirmation_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, это я", callback_data="confirm_identity"),
                InlineKeyboardButton(text="❌ Нет, это не я", callback_data="reject_identity")
            ]
        ]
    )

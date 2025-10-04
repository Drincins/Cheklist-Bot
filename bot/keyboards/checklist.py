# bot/keyboards/checklist.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def build_question_keyboard(question_type: str, current: int, selected: str | None = None) -> InlineKeyboardMarkup:
    """
    Клавиатура для вопроса: варианты ответа + коммент/фото + далее + назад.
    selected — ключ выбранного варианта: 'yes'/'no' | '1'..'5' | 'text'
    """
    def mark(label: str, key: str) -> str:
        return f"• {label}" if selected == key else label

    rows: list[list[InlineKeyboardButton]] = []
    if question_type == "yesno":
        rows.append([
            InlineKeyboardButton(text=mark("✅ Да", "yes"), callback_data="answer:yes"),
            InlineKeyboardButton(text=mark("❌ Нет", "no"), callback_data="answer:no"),
        ])
    elif question_type == "scale":
        rows.append([
            InlineKeyboardButton(text=mark(str(i), str(i)), callback_data=f"answer:{i}") for i in range(1, 6)
        ])
    else:
        rows.append([InlineKeyboardButton(text=mark("✍️ Ввести текст", "text"), callback_data="answer:text")])

    rows.append([
        InlineKeyboardButton(text="💬 Комментарий", callback_data=f"comment:{current}"),
        InlineKeyboardButton(text="📷 Фото",        callback_data=f"photo:{current}"),
    ])
    rows.append([InlineKeyboardButton(text="➡️ Далее", callback_data="continue_after_extra")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад к предыдущему", callback_data="prev_question")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_submode_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для подрежимов (ввод комментария/фото)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад к вопросу", callback_data="back_to_question")]
    ])

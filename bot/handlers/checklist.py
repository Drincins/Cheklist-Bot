from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from ..states import Form
from ..bot_logic import (
    get_checklists_for_user,
    get_questions_for_checklist,
    save_checklist_with_answers,
    get_checklist_by_id,
)
from ..keyboards.inline import get_checklists_keyboard
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
import asyncio

router = Router()

@router.message(F.text.startswith("Добро пожаловать"), Form.entering_phone)
async def show_checklists(message: types.Message, state: FSMContext):
    data = await state.get_data()
    checklists = get_checklists_for_user(data["user_id"])
    if not checklists:
        await message.answer("Нет доступных чек-листов.")
        return
    await message.answer("Выберите чек-лист для прохождения:", reply_markup=get_checklists_keyboard(checklists))
    await state.set_state(Form.show_checklists)

@router.callback_query(F.data.startswith("checklist:"), Form.show_checklists)
async def start_checklist(callback: types.CallbackQuery, state: FSMContext):
    checklist_id = int(callback.data.split(":")[1])
    questions = get_questions_for_checklist(checklist_id)
    if not questions:
        await callback.message.answer("У этого чек-листа нет вопросов.")
        await callback.answer()
        return
    await state.update_data(checklist_id=checklist_id, questions=questions, current=0, answers=[])

    # 🔽 Скрываем клавиатуру
    await callback.message.answer("📝 Начинаем чек-лист...", reply_markup=ReplyKeyboardRemove())

    await ask_next_question(callback.message, state)
    await state.set_state(Form.answering_question)
    await callback.answer()

def build_question_keyboard(question_type: str, current: int) -> InlineKeyboardMarkup:
    buttons = []
    if question_type == "yesno":
        buttons.append([
            InlineKeyboardButton(text="✅ Да", callback_data=f"answer:yes"),
            InlineKeyboardButton(text="❌ Нет", callback_data=f"answer:no"),
        ])
    elif question_type == "scale":
        buttons.append([
            InlineKeyboardButton(text=str(i), callback_data=f"answer:{i}") for i in range(1, 6)
        ])
    else:
        buttons.append([
            InlineKeyboardButton(text="✍️ Ввести текст", callback_data="answer:text")
        ])
    buttons.append([
        InlineKeyboardButton(text="❓", callback_data=f"hint:{current}"),
        InlineKeyboardButton(text="💬", callback_data=f"comment:{current}"),
        InlineKeyboardButton(text="📷", callback_data=f"photo:{current}")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def ask_next_question(message: types.Message, state: FSMContext):
    data = await state.get_data()
    questions = data["questions"]
    current = data["current"]

    if current >= len(questions):
        formatted_answers = [
            {
                "question_id": a["question_id"],
                "response_value": a["answer"],
                "comment": a.get("comment"),
                "photo_path": a.get("photo_path")
            }
            for a in data["answers"]
        ]
        await asyncio.to_thread(
            save_checklist_with_answers,
            user_id=data["user_id"],
            checklist_id=data["checklist_id"],
            answers=formatted_answers
        )
        checklist_info = get_checklist_by_id(data["checklist_id"])
        answers = data["answers"]
        keyboard = []

        if checklist_info and checklist_info.get("is_scored"):
            score = sum(int(a["answer"]) for q, a in zip(questions, answers) if q["type"] == "scale" and a["answer"].isdigit())
            await message.answer(f"✅ Чек-лист завершён.\n\n📊 Ваш результат: *{score}*", parse_mode="Markdown")
            keyboard = [
                [InlineKeyboardButton(text="🔍 Посмотреть подробности", callback_data="show_details")],
                [InlineKeyboardButton(text="➡️ Далее", callback_data="checklist_continue")]
            ]
        else:
            await message.answer("✅ Чек-лист завершён. Спасибо!")
            keyboard = [
                [InlineKeyboardButton(text="📋 Посмотреть ответы", callback_data="show_answers")],
                [InlineKeyboardButton(text="➡️ Далее", callback_data="checklist_continue")]
            ]
        await message.answer("Что дальше?", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await state.set_state(Form.show_checklists)
        return

    question = questions[current]
    await state.update_data(current=current + 1)
    keyboard = build_question_keyboard(question["type"], current)
    await message.answer(question["text"], reply_markup=keyboard)

@router.callback_query(F.data.startswith("answer:"), Form.answering_question)
async def handle_answer(callback: types.CallbackQuery, state: FSMContext):
    answer_value = callback.data.split(":")[1]
    if answer_value == "text":
        await callback.message.answer("Введите ваш ответ текстом:")
        await state.set_state(Form.manual_text_answer)
        await callback.answer()
        return
    data = await state.get_data()
    question = data["questions"][data["current"] - 1]
    data["answers"].append({
        "question_id": question["id"],
        "answer": answer_value,
        "comment": None,
        "photo_path": None
    })
    await state.update_data(answers=data["answers"])
    await ask_next_question(callback.message, state)
    await callback.answer()

@router.message(Form.manual_text_answer)
async def handle_manual_text_answer(message: types.Message, state: FSMContext):
    data = await state.get_data()
    question = data["questions"][data["current"] - 1]
    data["answers"].append({
        "question_id": question["id"],
        "answer": message.text.strip(),
        "comment": None,
        "photo_path": None
    })
    await state.update_data(answers=data["answers"])
    await ask_next_question(message, state)
    await state.set_state(Form.answering_question)

@router.callback_query(F.data.startswith("comment:"), Form.answering_question)
async def handle_comment_button(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(Form.adding_comment)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_question")]
    ])
    await callback.message.answer("💬 Введите ваш комментарий:", reply_markup=keyboard)
    await callback.answer()

@router.message(Form.adding_comment)
async def handle_comment_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    data["answers"][-1]["comment"] = message.text.strip()
    await state.update_data(answers=data["answers"])
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Далее", callback_data="continue_after_extra")],
        [InlineKeyboardButton(text="📷 Добавить фото", callback_data="photo:same")]
    ])
    await message.answer("✅ Ваш комментарий записан.", reply_markup=keyboard)

@router.callback_query(F.data.startswith("photo:"), Form.answering_question)
async def handle_photo_button(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(Form.adding_photo)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_question")]
    ])
    await callback.message.answer("📷 Отправьте фото:", reply_markup=keyboard)
    await callback.answer()

@router.message(Form.adding_photo)
async def handle_photo_input(message: types.Message, state: FSMContext):
    data = await state.get_data()

    if message.photo:
        file_id = message.photo[-1].file_id
        data["answers"][-1]["photo_path"] = file_id
        await state.update_data(answers=data["answers"])
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➡️ Далее", callback_data="continue_after_extra")],
            [InlineKeyboardButton(text="💬 Оставить комментарий", callback_data="comment:same")]
        ])
        await message.answer("✅ Фото успешно загружено.", reply_markup=keyboard)
    else:
        await message.answer("Пожалуйста, отправьте фото.")

@router.callback_query(F.data == "back_to_question")
async def handle_back_to_question(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("⬅️ Возвращаемся к вопросу.")
    await ask_next_question(callback.message, state)
    await state.set_state(Form.answering_question)
    await callback.answer()

@router.callback_query(F.data == "continue_after_extra")
async def handle_continue_after_extra(callback: types.CallbackQuery, state: FSMContext):
    await ask_next_question(callback.message, state)
    await state.set_state(Form.answering_question)
    await callback.answer()

@router.callback_query(F.data == "comment:same")
async def handle_comment_same(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(Form.adding_comment)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_question")]
    ])
    await callback.message.answer("💬 Введите ваш комментарий:", reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data == "photo:same")
async def handle_photo_same(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(Form.adding_photo)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_question")]
    ])
    await callback.message.answer("📷 Отправьте фото:", reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data == "hint:")
async def handle_hint(callback: types.CallbackQuery):
    await callback.answer("ℹ️ Здесь будет пояснение к вопросу.", show_alert=True)

@router.callback_query(F.data == "show_details")
async def handle_show_details(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    questions = data["questions"]
    answers = data["answers"]
    text = "🔍 Подробные ответы:\n\n"
    for q, a in zip(questions, answers):
        text += f"— {q['text']}: *{a['answer']}*\n"
    await callback.message.answer(text, parse_mode="Markdown")

    # 🔁 Добавим повтор кнопки "Далее"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Далее", callback_data="checklist_continue")]
    ])
    await callback.message.answer("Что дальше?", reply_markup=keyboard)

    await callback.answer()

@router.callback_query(F.data == "show_answers")
async def handle_show_answers(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    questions = data["questions"]
    answers = data["answers"]
    text = "📋 Ваши ответы:\n\n"
    for q, a in zip(questions, answers):
        text += f"— {q['text']}: *{a['answer']}*\n"
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "checklist_continue")
async def handle_continue(callback: types.CallbackQuery, state: FSMContext):
    from keyboards.reply import authorized_keyboard
    await callback.message.answer(
        "📋 Главное меню:",
        reply_markup=authorized_keyboard
    )
    await callback.answer()



from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from states import Form
from bot_logic import get_checklists_for_user, get_questions_for_checklist
from bot_logic import save_checklist_with_answers
from keyboards.inline import get_checklists_keyboard, get_yes_no_keyboard, get_scale_keyboard
import asyncio



router = Router()

# === Показываем чек-листы после авторизации ===
@router.message(F.text.startswith("Добро пожаловать"), Form.entering_phone)
async def show_checklists(message: types.Message, state: FSMContext):
    data = await state.get_data()
    checklists = get_checklists_for_user(data["user_id"])

    if not checklists:
        await message.answer("Нет доступных чек-листов.")
        await state.clear()
        return

    await message.answer("Выберите чек-лист для прохождения:", reply_markup=get_checklists_keyboard(checklists))
    await state.set_state(Form.show_checklists)

# === Начинаем чек-лист ===
@router.callback_query(F.data.startswith("checklist:"), Form.show_checklists)
async def start_checklist(callback: types.CallbackQuery, state: FSMContext):
    checklist_id = int(callback.data.split(":")[1])
    questions = get_questions_for_checklist(checklist_id)

    if not questions:
        await callback.message.answer("У этого чек-листа нет вопросов.")
        return

    await state.update_data(checklist_id=checklist_id, questions=questions, current=0, answers=[])
    await ask_next_question(callback.message, state)
    await state.set_state(Form.answering_question)
    await callback.answer()

# === Следующий вопрос ===
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

        await asyncio.to_thread(save_checklist_with_answers, 
                                user_id=data["user_id"], 
                                checklist_id=data["checklist_id"], 
                                answers=formatted_answers)

        await message.answer("✅ Чек-лист завершён. Спасибо!")
        await state.clear()
        return


    question = questions[current]
    await state.update_data(current=current + 1)

    if question["type"] == "yesno":
        await message.answer(question["text"], reply_markup=get_yes_no_keyboard())
    elif question["type"] == "scale":
        await message.answer(question["text"], reply_markup=get_scale_keyboard())
    else:
        await message.answer(question["text"])

# === Ответ на кнопку ===
@router.callback_query(F.data.startswith("answer:"), Form.answering_question)
async def handle_answer(callback: types.CallbackQuery, state: FSMContext):
    answer = callback.data.split(":")[1]
    data = await state.get_data()
    question = data["questions"][data["current"] - 1]
    data["answers"].append({
        "question_id": question["id"],
        "answer": answer,
        "comment": None,
        "photo_path": None
    })
    await state.update_data(answers=data["answers"])
    await callback.message.answer("Хотите оставить комментарий? Напишите или отправьте '—' чтобы пропустить.")
    await state.set_state(Form.adding_comment)
    await callback.answer()

# === Ответ текстом ===
@router.message(Form.answering_question)
async def handle_text_answer(message: types.Message, state: FSMContext):
    data = await state.get_data()
    question = data["questions"][data["current"] - 1]
    data["answers"].append({
        "question_id": question["id"],
        "answer": message.text.strip(),
        "comment": None,
        "photo_path": None
    })
    await state.update_data(answers=data["answers"])
    await message.answer("Хотите оставить комментарий? Напишите или отправьте '—' чтобы пропустить.")
    await state.set_state(Form.adding_comment)

# === Комментарий ===
@router.message(Form.adding_comment)
async def handle_comment(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if message.text.strip() != "—":
        data["answers"][-1]["comment"] = message.text.strip()
        await state.update_data(answers=data["answers"])

    await message.answer("Хотите прикрепить фото? Отправьте фото или '—' чтобы пропустить.")
    await state.set_state(Form.adding_photo)

# === Фото ===
@router.message(Form.adding_photo)
async def handle_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()

    if message.photo:
        file_id = message.photo[-1].file_id
        data["answers"][-1]["photo_path"] = file_id
        await state.update_data(answers=data["answers"])
    elif message.text.strip() != "—":
        await message.answer("Пожалуйста, отправьте фото или '—' чтобы пропустить.")
        return

    await ask_next_question(message, state)
    await state.set_state(Form.answering_question) 
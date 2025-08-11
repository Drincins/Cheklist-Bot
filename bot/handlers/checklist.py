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
from ..keyboards.reply import authorized_keyboard

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

    # answers_map: question_id -> {"answer": None|str, "comment": None|str, "photo_path": None|str}
    answers_map = {}

    await state.update_data(
        checklist_id=checklist_id,
        questions=questions,
        current=0,
        answers_map=answers_map,
    )

    # 🔽 Скрываем клавиатуру
    await callback.message.answer("📝 Начинаем чек-лист...", reply_markup=ReplyKeyboardRemove())

    await ask_next_question(callback.message, state)   # НЕ инкрементим current здесь
    await state.set_state(Form.answering_question)
    await callback.answer()

def _question_text(question: dict, draft: dict) -> str:
    """Текст вопроса + индикаторы введённых данных."""
    extra = []
    if draft.get("answer") is not None:
        extra.append(f"🟩 Ответ: *{draft['answer']}*")
    if draft.get("comment"):
        extra.append("💬 Комментарий добавлен")
    if draft.get("photo_path"):
        extra.append("📷 Фото добавлено")
    suffix = ("\n\n" + "\n".join(extra)) if extra else ""
    return f"{question['text']}{suffix}"

def _answers_summary_text(questions: list[dict], answers_map: dict) -> str:
    lines = ["🗂 *Ваши ответы:*\n"]
    yes_total = yes_cnt = 0
    scale_vals = []

    for q in questions:
        d = answers_map.get(q["id"], {})
        a = d.get("answer")
        lines.append(f"— {q['text']}: *{a if a is not None else '—'}*")
        # простая метрика
        if q["type"] == "yesno":
            yes_total += 1
            if str(a).lower() == "yes":
                yes_cnt += 1
        elif q["type"] == "scale" and a is not None:
            try:
                scale_vals.append(float(a))
            except Exception:
                pass

    parts = []
    if yes_total:
        parts.append(f"{round(100*yes_cnt/yes_total)}% «да»")
    if scale_vals:
        # шкала 1..5 → % от максимума
        parts.append(f"{round(100*(sum(scale_vals)/len(scale_vals))/5)}% шкала")
    if parts:
        lines.append("\n📊 Итог: " + " / ".join(parts))

    return "\n".join(lines)

def build_question_keyboard(question_type: str, current: int, selected: str | None = None) -> InlineKeyboardMarkup:
    """Обычный режим вопроса (ответ/коммент/фото/далее + назад к предыдущему)."""
    def mark(label: str, key: str) -> str:
        # нейтральная метка при выборе
        return f"• {label}" if selected == key else label

    rows = []
    if question_type == "yesno":
        rows.append([
            InlineKeyboardButton(text=mark("✅ Да",  "yes"), callback_data="answer:yes"),
            InlineKeyboardButton(text=mark("❌ Нет", "no"),  callback_data="answer:no"),
        ])
    elif question_type == "scale":
        rows.append([InlineKeyboardButton(text=mark(str(i), str(i)), callback_data=f"answer:{i}") for i in range(1, 6)])
    else:
        rows.append([InlineKeyboardButton(text=mark("✍️ Ввести текст", "text"), callback_data="answer:text")])

    rows.append([
        InlineKeyboardButton(text="💬 Комментарий", callback_data=f"comment:{current}"),
        InlineKeyboardButton(text="📷 Фото",        callback_data=f"photo:{current}"),
    ])
    rows.append([
        InlineKeyboardButton(text="➡️ Далее", callback_data="continue_after_extra"),
    ])
    # новая кнопка в самом низу
    rows.append([
        InlineKeyboardButton(text="⬅️ Назад к предыдущему", callback_data="prev_question"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def build_submode_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для подрежимов (ввод комментария/фото)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад к вопросу", callback_data="back_to_question")]
    ])



async def ask_next_question(message: types.Message, state: FSMContext):
    data = await state.get_data()
    questions = data["questions"]
    current = data["current"]
    answers_map = data.get("answers_map", {})
    q_msg_id = data.get("q_msg_id")

    # завершение
    if current >= len(questions):
        formatted_answers = []
        for q in questions:
            d = answers_map.get(q["id"], {})
            formatted_answers.append({
                "question_id": q["id"],
                "response_value": d.get("answer"),
                "comment": d.get("comment"),
                "photo_path": d.get("photo_path"),
            })
        await asyncio.to_thread(
            save_checklist_with_answers,
            user_id=data["user_id"],
            checklist_id=data["checklist_id"],
            answers=formatted_answers
        )
        await message.answer("✅ Чек-лист завершён. Спасибо!")

        next_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📄 Посмотреть ответы", callback_data="show_answers_here")],
            [InlineKeyboardButton(text="➡️ Далее", callback_data="checklist_continue")],
        ])
        nxt = await message.answer("Что дальше?", reply_markup=next_kb)
        await state.update_data(next_actions_msg_id=nxt.message_id)
        await state.set_state(Form.show_checklists)
        return


    # показать/перерисовать текущий вопрос
    question = questions[current]
    qid = question["id"]
    draft = answers_map.setdefault(qid, {"answer": None, "comment": None, "photo_path": None})
    await state.update_data(answers_map=answers_map)

    text = _question_text(question, draft)

    # какой вариант подсветить точкой
    qtype = question["type"]
    if qtype in ("yesno", "scale"):
        selected_key = draft.get("answer")               # 'yes'/'no' или '1'..'5'
    else:
        selected_key = "text" if draft.get("answer") is not None else None

    kb = build_question_keyboard(qtype, current, selected=selected_key)

    if q_msg_id:
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=q_msg_id,
            text=text,
            parse_mode="Markdown"
        )
        await message.bot.edit_message_reply_markup(
            chat_id=message.chat.id,
            message_id=q_msg_id,
            reply_markup=kb
        )
    else:
        sent = await message.answer(text, reply_markup=kb, parse_mode="Markdown")
        await state.update_data(q_msg_id=sent.message_id)




@router.callback_query(F.data.startswith("answer:"), Form.answering_question)
async def handle_answer(callback: types.CallbackQuery, state: FSMContext):
    value = callback.data.split(":")[1]  # 'yes'/'no' | '1'..'5' | 'text'
    data = await state.get_data()
    questions = data["questions"]
    current = data["current"]
    answers_map = data.get("answers_map", {})
    q_msg_id = data.get("q_msg_id")

    question = questions[current]
    qid = question["id"]

    # Если выбран текстовый ответ — переходим в режим ввода, редактируя то же сообщение
    if value == "text":
        await state.set_state(Form.manual_text_answer)
        await callback.bot.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=q_msg_id or callback.message.message_id,
            text="✍️ Введите ваш ответ текстом:",
        )
        await callback.bot.edit_message_reply_markup(
            chat_id=callback.message.chat.id,
            message_id=q_msg_id or callback.message.message_id,
            reply_markup=build_submode_keyboard()
        )
        await callback.answer()
        return

    # Сохраняем выбранный вариант в черновик (yes/no/scale)
    draft = answers_map.setdefault(qid, {"answer": None, "comment": None, "photo_path": None})
    draft["answer"] = value
    answers_map[qid] = draft
    await state.update_data(answers_map=answers_map)

    # Подсветим выбранную кнопку «серой точкой» в той же клавиатуре
    kb = build_question_keyboard(question["type"], current, selected=value)
    await callback.bot.edit_message_reply_markup(
        chat_id=callback.message.chat.id,
        message_id=q_msg_id or callback.message.message_id,
        reply_markup=kb
    )
    await callback.answer("Ответ записан. Можно добавить комментарий/фото или нажать «Далее».")

# helper — тихо удаляем любое сообщение
async def _safe_delete(msg: types.Message):
    try:
        await msg.delete()
    except Exception:
        pass



@router.message(Form.manual_text_answer)
async def handle_manual_text_answer(message: types.Message, state: FSMContext):
    data = await state.get_data()
    questions = data["questions"]; current = data["current"]
    answers_map = data.get("answers_map", {})
    qid = questions[current]["id"]

    # сохраняем ответ
    answers_map.setdefault(qid, {"answer": None, "comment": None, "photo_path": None})["answer"] = message.text.strip()
    await state.update_data(answers_map=answers_map)

    # удаляем пользовательское сообщение, чтобы вопрос остался последним
    await _safe_delete(message)

    # возвращаемся в режим вопроса и перерисовываем единый экран
    await state.set_state(Form.answering_question)
    await ask_next_question(message, state)



@router.callback_query(F.data.startswith("comment:"), Form.answering_question)
async def handle_comment_button(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    q_msg_id = data.get("q_msg_id")
    await state.set_state(Form.adding_comment)
    await state.update_data(submode="comment")

    await callback.bot.edit_message_text(
        chat_id=callback.message.chat.id,
        message_id=q_msg_id or callback.message.message_id,
        text="💬 Введите ваш комментарий:",
    )
    await callback.bot.edit_message_reply_markup(
        chat_id=callback.message.chat.id,
        message_id=q_msg_id or callback.message.message_id,
        reply_markup=build_submode_keyboard()
    )
    await callback.answer()

@router.message(Form.adding_comment)
async def handle_comment_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    questions = data["questions"]; current = data["current"]
    answers_map = data.get("answers_map", {})

    qid = questions[current]["id"]
    answers_map.setdefault(qid, {"answer": None, "comment": None, "photo_path": None})["comment"] = message.text.strip()
    await state.update_data(answers_map=answers_map)

    # удаляем сообщение с комментарием, чтобы вопрос остался последним
    await _safe_delete(message)

    # вернуть экран вопроса
    await state.set_state(Form.answering_question)
    await ask_next_question(message, state)

@router.callback_query(F.data.startswith("photo:"), Form.answering_question)
async def handle_photo_button(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    q_msg_id = data.get("q_msg_id")
    await state.set_state(Form.adding_photo)

    await callback.bot.edit_message_text(
        chat_id=callback.message.chat.id,
        message_id=q_msg_id or callback.message.message_id,
        text="📷 Отправьте фото:",
    )
    await callback.bot.edit_message_reply_markup(
        chat_id=callback.message.chat.id,
        message_id=q_msg_id or callback.message.message_id,
        reply_markup=build_submode_keyboard()
    )
    await callback.answer()

@router.message(Form.adding_photo)
async def handle_photo_input(message: types.Message, state: FSMContext):
    if not message.photo:
        await message.answer("Пожалуйста, отправьте фото.")
        return

    data = await state.get_data()
    questions = data["questions"]; current = data["current"]
    answers_map = data.get("answers_map", {})
    qid = questions[current]["id"]

    answers_map.setdefault(qid, {"answer": None, "comment": None, "photo_path": None})["photo_path"] = message.photo[-1].file_id
    await state.update_data(answers_map=answers_map)

    # удаляем сообщение с фото
    await _safe_delete(message)

    # вернуть экран вопроса
    await state.set_state(Form.answering_question)
    await ask_next_question(message, state)


@router.callback_query(F.data == "back_to_question")
async def handle_back_to_question(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(Form.answering_question)
    await ask_next_question(callback.message, state)
    await callback.answer()

@router.callback_query(F.data == "continue_after_extra")
async def handle_continue_after_extra(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    questions = data["questions"]
    current = data["current"]
    answers_map = data.get("answers_map", {})
    q_msg_id = data.get("q_msg_id")

    # 1) Проверяем, что ответ есть
    qid = questions[current]["id"]
    has_answer = answers_map.get(qid, {}).get("answer") is not None
    if not has_answer:
        await callback.answer("Сначала выберите ответ на вопрос.", show_alert=True)
        return

    # 2) Отключаем клавиатуру у текущего вопроса, чтобы по ней не тыкали
    try:
        if q_msg_id:
            await callback.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=q_msg_id,
                reply_markup=None
            )
    except Exception:
        pass

    # 3) Двигаем указатель, очищаем q_msg_id (дальше будет новое/другое сообщение)
    new_current = current + 1
    await state.update_data(current=new_current, q_msg_id=None)

    # 4) Переходим дальше (ask_next_question сам завершит чек-лист, если вопросов больше нет)
    await ask_next_question(callback.message, state)
    await callback.answer()

@router.callback_query(F.data == "prev_question", Form.answering_question)
async def handle_prev_question(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    current = data["current"]
    if current <= 0:
        await callback.answer("Это первый вопрос.", show_alert=True)
        return
    await state.update_data(current=current - 1)
    await ask_next_question(callback.message, state)
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

@router.callback_query(F.data.startswith("hint:"))
async def handle_hint(callback: types.CallbackQuery):
    await callback.answer("ℹ️ Здесь будет пояснение к вопросу.", show_alert=True)


@router.callback_query(F.data == "show_details")
async def handle_show_details(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    questions = data["questions"]
    answers_map = data.get("answers_map", {})

    text = "🔍 Подробные ответы:\n\n"
    for q in questions:
        d = answers_map.get(q["id"], {})
        ans = d.get("answer")
        comment = d.get("comment")
        photo = "есть" if d.get("photo_path") else "нет"
        text += f"— {q['text']}: *{ans if ans is not None else '—'}*  | 💬 {comment or '—'} | 📷 {photo}\n"

    await callback.message.answer(text, parse_mode="Markdown")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Далее", callback_data="checklist_continue")]
    ])
    await callback.message.answer("Что дальше?", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "show_answers_here")
async def handle_show_answers_here(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    msg_id = data.get("next_actions_msg_id")
    questions = data.get("questions", [])
    answers_map = data.get("answers_map", {})

    text = _answers_summary_text(questions, answers_map)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_next_actions")],
    ])

    if msg_id:
        await callback.bot.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=msg_id,
            text=text,
            parse_mode="Markdown"
        )
        await callback.bot.edit_message_reply_markup(
            chat_id=callback.message.chat.id,
            message_id=msg_id,
            reply_markup=kb
        )
    else:
        # запасной вариант, если msg_id потеряли
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)

    await callback.answer()

@router.callback_query(F.data == "back_to_next_actions")
async def handle_back_to_next_actions(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    msg_id = data.get("next_actions_msg_id")

    next_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 Посмотреть ответы", callback_data="show_answers_here")],
        [InlineKeyboardButton(text="➡️ Далее",              callback_data="checklist_continue")],
    ])

    if msg_id:
        await callback.bot.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=msg_id,
            text="Что дальше?"
        )
        await callback.bot.edit_message_reply_markup(
            chat_id=callback.message.chat.id,
            message_id=msg_id,
            reply_markup=next_kb
        )
    else:
        await callback.message.answer("Что дальше?", reply_markup=next_kb)

    await callback.answer()


@router.callback_query(F.data == "checklist_continue")
async def handle_continue(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "📋 Главное меню:",
        reply_markup=authorized_keyboard
    )
    await callback.answer()



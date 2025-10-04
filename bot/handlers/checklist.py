import asyncio
import html
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from aiogram import Router, types, F, Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from ..states import Form
from ..services.auth import AuthService
from ..services.checklists import ChecklistsService
from ..keyboards.inline import get_checklists_keyboard
from ..keyboards.reply import authorized_keyboard
from .start import send_main_menu
from ..utils.checklist_mode import group_questions_by_section
from ..report_data import get_attempt_data, format_attempt_result, AttemptData, AnswerRow

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove

router = Router()

auth_service = AuthService()
checklists_service = ChecklistsService()

MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", "media"))
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)

_RESERVED_TEXT_COMMANDS = {
    "🏠 Домой",
    "🚪 Выйти",
    "🚪 выйти",
    "✅ Доступные чек-листы",
    "✅ доступные чек-листы",
    "📋 Пройденные чек-листы",
    "📋 пройденные чек-листы",
    "ℹ️ Обо мне",
    "ℹ️ обо мне",
}

_YESNO_TYPES = {"yesno", "yes_no", "boolean", "bool", "yn"}
_SCALE_TYPES = {"scale", "rating"}


def _escape(text: str | None) -> str:
    return html.escape(text or "")


def _fmt_points(value) -> str:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    text = f"{num:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def _is_answer_filled(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _count_answered(answers_map: dict[int, dict]) -> int:
    count = 0
    for draft in answers_map.values():
        if not isinstance(draft, dict):
            continue
        if _is_answer_filled(draft.get("answer")):
            count += 1
    return count


def _normalize_answers_map(raw: dict | None) -> dict[int, dict[str, Any]]:
    normalized: dict[int, dict[str, Any]] = {}
    if isinstance(raw, dict):
        for key, draft in raw.items():
            try:
                qid = int(key)
            except (TypeError, ValueError):
                continue
            if not isinstance(draft, dict):
                draft = {"answer": draft, "comment": None, "photo_path": None}
            normalized[qid] = {
                "answer": draft.get("answer"),
                "comment": draft.get("comment"),
                "photo_path": draft.get("photo_path"),
            }
    return normalized


def _first_unanswered_index(questions: list[dict], answers_map: dict[int, dict]) -> int:
    for idx, question in enumerate(questions):
        qid = question.get("id")
        if qid is None:
            continue
        draft = answers_map.get(qid, {})
        if not isinstance(draft, dict):
            draft = {}
        if not _is_answer_filled(draft.get("answer")):
            return idx
    return len(questions)


def _first_unanswered_block_index(sections: list[dict], answers_map: dict[int, dict]) -> int:
    for idx, section in enumerate(sections):
        for question in section.get("items", []):
            qid = question.get("id")
            if qid is None:
                continue
            draft = answers_map.get(qid, {})
            if not isinstance(draft, dict):
                draft = {}
            if not _is_answer_filled(draft.get("answer")):
                return idx
    return 0


async def _store_photo_locally(bot: Bot, file_id: str, attempt_id: int | None, question_id: int) -> str | None:
    """Скачиваем фото из Telegram и размещаем под MEDIA_ROOT. Возвращаем относительный путь."""
    if not file_id:
        return None

    try:
        file_info = await bot.get_file(file_id)
    except TelegramBadRequest:
        return None
    except Exception:
        return None

    suffix = Path(getattr(file_info, "file_path", "")).suffix or ".jpg"
    filename = f"attempt_{attempt_id or 'unknown'}_q{question_id}_{uuid.uuid4().hex}{suffix}"
    full_path = MEDIA_ROOT / filename

    try:
        await bot.download(file_id, destination=str(full_path))
    except Exception:
        return None

    rel_path = MEDIA_ROOT / filename
    return str(rel_path)

@router.message(F.text.startswith("Добро пожаловать"), Form.entering_login)
async def show_checklists(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id")
    if not user_id:
        await message.answer("Сначала пройдите авторизацию через /start.")
        return

    checklists = await asyncio.to_thread(auth_service.get_user_checklists, user_id)
    if not checklists:
        await message.answer("Нет доступных чек-листов.")
        return
    await state.update_data(checklists_map={str(c["id"]): c["name"] for c in checklists})
    await message.answer("Выберите чек-лист для прохождения:", reply_markup=get_checklists_keyboard(checklists))
    await state.set_state(Form.show_checklists)


@router.message(F.text.in_({"✅ Доступные чек-листы", "✅ доступные чек-листы"}))
async def show_checklists_on_command(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id")
    if not user_id:
        await message.answer("⚠️ Сначала авторизуйтесь через /start.")
        return

    checklists = await asyncio.to_thread(auth_service.get_user_checklists, user_id)
    if not checklists:
        await message.answer("🙁 У вас пока нет доступных чек-листов.")
        return

    await state.update_data(checklists_map={str(c["id"]): c["name"] for c in checklists})
    await message.answer("📋 Доступные чек-листы:", reply_markup=get_checklists_keyboard(checklists))
    await state.set_state(Form.show_checklists)

@router.callback_query(F.data.startswith("checklist:"), Form.show_checklists)
async def start_checklist(callback: types.CallbackQuery, state: FSMContext):
    checklist_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    user_id = data.get("user_id")
    if not user_id:
        await callback.answer("Авторизуйтесь заново", show_alert=True)
        return

    questions = await asyncio.to_thread(
        checklists_service.get_questions_for_checklist,
        checklist_id,
    )
    if not questions:
        await callback.message.answer("У этого чек-листа нет вопросов.")
        await callback.answer()
        return

    checklists_map = data.get("checklists_map", {})
    checklist_name = checklists_map.get(str(checklist_id)) or f"Чек-лист #{checklist_id}"

    draft_attempt_id = None
    existing_attempt_id = data.get("attempt_id")
    existing_checklist_id = data.get("checklist_id") or data.get("pending_checklist_id")
    if existing_attempt_id and existing_checklist_id == checklist_id:
        draft_attempt_id = existing_attempt_id
    else:
        draft_attempt_id = await asyncio.to_thread(
            checklists_service.find_draft_attempt,
            user_id,
            checklist_id,
        )
    answered_count = None
    answers_from_draft: dict[int, dict[str, Any]] = {}
    draft_department = None
    if draft_attempt_id:
        draft_answers = await asyncio.to_thread(
            checklists_service.get_attempt_answers,
            draft_attempt_id,
        )
        answers_from_draft = _normalize_answers_map(draft_answers)
        answered_count = _count_answered(answers_from_draft)
        draft_department = await asyncio.to_thread(
            checklists_service.get_draft_department,
            draft_attempt_id,
        )

    user = data.get("user", {})
    departments = user.get("departments") or []
    departments = [d for d in departments if d]
    if departments:
        departments = list(dict.fromkeys(departments))

    await state.update_data(
        pending_checklist_id=checklist_id,
        checklist_name=checklist_name,
        questions=questions,
        question_map={q.get("id"): q for q in questions if q.get("id") is not None},
        answers_map=answers_from_draft if answers_from_draft else {},
        current=0,
        attempt_id=None,
        department_options=departments,
        selected_department=draft_department,
        q_msg_id=None,
        next_actions_msg_id=None,
        exit_confirm_message_id=None,
        block_sections=None,
        block_question_messages={},
        block_header_message_id=None,
        block_nav_message_id=None,
        resume_attempt_id=draft_attempt_id,
        resume_prompt_message_id=None,
        resume_answered_count=answered_count,
    )

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if draft_attempt_id:
        total_questions = len(questions)
        resume_lines = [
            f"⏸ У вас уже есть незавершённое прохождение «{_escape(checklist_name)}»."
        ]
        if answered_count:
            resume_lines.append(f"Заполнено: {answered_count} из {total_questions} вопросов.")
        else:
            resume_lines.append(f"Всего вопросов: {total_questions}. Ответы ещё не сохранены.")
        if draft_department:
            resume_lines.append(f"Выбрано подразделение: {_escape(draft_department)}")
        resume_lines.append("Продолжить или начать заново?")
        prompt = await callback.message.answer(
            "\n".join(resume_lines),
            reply_markup=_build_resume_keyboard(),
            parse_mode="HTML",
        )
        await state.update_data(resume_prompt_message_id=prompt.message_id)
        await state.set_state(Form.confirming_resume)
        await callback.answer()
        return

    await _prompt_department_choice(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "resume:continue", Form.confirming_resume)
async def handle_resume_continue(callback: types.CallbackQuery, state: FSMContext):
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await _safe_delete(callback.message)
    data = await state.get_data()
    await state.update_data(
        resume_prompt_message_id=None,
        resume_answered_count=None,
    )
    department = data.get("selected_department")
    if department:
        await _prompt_mode_selection(callback.message, state, department)
    else:
        await _prompt_department_choice(callback.message, state)
    await callback.answer("Продолжаем заполнение.")


@router.callback_query(F.data == "resume:new", Form.confirming_resume)
async def handle_resume_new(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    attempt_id = data.get("resume_attempt_id")
    if attempt_id:
        await asyncio.to_thread(checklists_service.discard, attempt_id)

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await _safe_delete(callback.message)
    await state.update_data(
        resume_attempt_id=None,
        resume_prompt_message_id=None,
        resume_answered_count=None,
        attempt_id=None,
        answers_map={},
        selected_department=None,
    )

    await _prompt_department_choice(callback.message, state)
    await callback.answer("Начинаем заново.")


def _question_text(question: dict, draft: dict) -> str:
    """Текст вопроса + индикаторы введённых данных."""
    base = _escape(str(question.get("text", "")))
    parts = [base]

    comment_required = bool(question.get("require_comment"))
    photo_required = bool(question.get("require_photo"))
    comment_present = bool(draft.get("comment"))
    photo_present = bool(draft.get("photo_path"))

    req_lines: list[str] = []
    if comment_required:
        if comment_present:
            req_lines.append("✅ Комментарий добавлен")
        else:
            req_lines.append("💬 Требуется комментарий")
    if photo_required:
        if photo_present:
            req_lines.append("✅ Фото добавлено")
        else:
            req_lines.append("📷 Требуется фото")
    if req_lines:
        parts.append("\n".join(req_lines))

    extra = []
    answer = draft.get("answer")
    qtype = (question.get("type") or "").lower().strip()
    if answer is not None:
        answer_str = str(answer).strip()
        if answer_str == "":
            extra.append("🟦 Ответ: <b>—</b>")
        else:
            lower = answer_str.lower()
            yes_values = {"yes", "да", "true", "1"}
            no_values = {"no", "нет", "false", "0"}

            if qtype in {"yesno", "yes_no", "boolean", "bool", "yn"}:
                if lower in yes_values:
                    emoji = "🟩"
                elif lower in no_values:
                    emoji = "🟥"
                else:
                    emoji = "🟪"
            elif qtype in {"scale", "rating"}:
                emoji = "🟨"
            else:
                emoji = "🟪"

            extra.append(f"{emoji} Ответ: <b>{_escape(answer_str)}</b>")
    if comment_present and not comment_required:
        extra.append("💬 Комментарий добавлен")
    if photo_present and not photo_required:
        extra.append("📷 Фото добавлено")
    if extra:
        parts.append("\n".join(extra))

    return "\n\n".join(parts)


def _resolve_question(data: dict, qid: int | None = None) -> tuple[int | None, dict | None]:
    """Находит вопрос по id или по текущему индексу."""
    questions = data.get("questions") or []
    question_map: dict | None = data.get("question_map")

    if qid is not None:
        if question_map and qid in question_map:
            return qid, question_map[qid]
        for item in questions:
            if item.get("id") == qid:
                return qid, item
        return None, None

    current = data.get("current")
    if current is not None and 0 <= current < len(questions):
        question = questions[current]
        return question.get("id"), question

    return None, None

def _answers_summary_text(
    questions: list[dict],
    answers_map: dict,
    attempt_data: AttemptData | None = None,
) -> str:
    lines = ["🗂 <b>Ваши ответы:</b>"]
    yes_total = yes_cnt = 0
    scale_vals = []

    rows_by_index: dict[int, AnswerRow] = {}
    if attempt_data and attempt_data.answers:
        rows_by_index = {row.number - 1: row for row in attempt_data.answers}

    for idx, q in enumerate(questions):
        d = answers_map.get(q["id"], {})
        a = d.get("answer")
        answer_text = "—" if a is None else _escape(str(a))
        suffix = ""
        row = rows_by_index.get(idx)
        if attempt_data and attempt_data.is_scored and row and row.weight is not None:
            score_value = row.score if row.score is not None else 0.0
            suffix = f" ({_fmt_points(score_value)}/{_fmt_points(row.weight)})"
        lines.append(f"— {_escape(str(q['text']))}: <b>{answer_text}</b>{suffix}")
        if not attempt_data or not attempt_data.is_scored:
            if q["type"] == "yesno":
                yes_total += 1
                if str(a).lower() == "yes":
                    yes_cnt += 1
            elif q["type"] == "scale" and a is not None:
                try:
                    scale_vals.append(float(a))
                except Exception:
                    pass

    if attempt_data and attempt_data.is_scored:
        result_line = format_attempt_result(attempt_data)
        if result_line:
            lines.append("")
            lines.append(f"📊 Результат: <b>{_escape(result_line)}</b>")
    else:
        parts = []
        if yes_total:
            parts.append(f"{round(100*yes_cnt/yes_total)}% «да»")
        if scale_vals:
            parts.append(f"{round(100*(sum(scale_vals)/len(scale_vals))/5)}% шкала")
        if parts:
            lines.append("")
            lines.append("📊 Итог: " + " / ".join(parts))

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
    rows.append([
        InlineKeyboardButton(text="⬅️ Назад к предыдущему", callback_data="prev_question"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def build_submode_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для подрежимов (ввод комментария/фото)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад к вопросу", callback_data="back_to_question")]
    ])


def _build_department_keyboard(options: list[str]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=opt, callback_data=f"dept_select:{idx}")]
            for idx, opt in enumerate(options)]
    rows.append([InlineKeyboardButton(text="➕ Другое", callback_data="dept_other")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👀 Показать весь чек-лист", callback_data="mode:full")],
        [InlineKeyboardButton(text="▶️ Пройти по порядку", callback_data="mode:start")],
        [InlineKeyboardButton(text="🔠 Пройти по блокам", callback_data="mode:blocks")],
        [InlineKeyboardButton(text="⬅️ Выбрать другой объект", callback_data="mode:back")],
    ])


def _sections_word(value: int) -> str:
    if value % 10 == 1 and value % 100 != 11:
        return "раздел"
    if 2 <= value % 10 <= 4 and not (10 <= value % 100 <= 20):
        return "раздела"
    return "разделов"


def _format_full_preview_page(sections: list[dict], index: int) -> str:
    total = len(sections)
    section = sections[index]
    lines = [
        f"📜 <b>Полный список вопросов</b> ({total} {_sections_word(total)})",
        f"<i>Раздел {index + 1} из {total}</i>",
        "",
        f"<b>{_escape(section['title'])}</b>",
    ]
    for idx, question in enumerate(section.get("questions", []), start=1):
        lines.append(f"{idx}. {_escape(question)}")

    return "\n".join(lines)


def _build_full_preview_keyboard(index: int, total: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    if total > 1:
        nav_row: list[InlineKeyboardButton] = []
        nav_row.append(
            InlineKeyboardButton(
                text="⬅️",
                callback_data=f"mode:full_page:{index - 1}" if index > 0 else "mode:full_page:noop",
            )
        )
        nav_row.append(
            InlineKeyboardButton(text=f"{index + 1}/{total}", callback_data="mode:full_page:noop")
        )
        nav_row.append(
            InlineKeyboardButton(
                text="➡️",
                callback_data=f"mode:full_page:{index + 1}" if index < total - 1 else "mode:full_page:noop",
            )
        )
        rows.append(nav_row)
    else:
        rows.append([
            InlineKeyboardButton(text="1/1", callback_data="mode:full_page:noop"),
        ])

    rows.append([InlineKeyboardButton(text="▶️ Пройти по порядку", callback_data="mode:start")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="mode:full_back")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_block_question_keyboard(question: dict, qid: int, draft: dict) -> InlineKeyboardMarkup:
    """Клавиатура для режима прохождения по блокам."""
    answer = draft.get("answer")
    answer_str = str(answer).lower() if answer is not None else None
    comment = draft.get("comment")
    photo = draft.get("photo_path")
    qtype = (question.get("type") or "").lower().strip()

    def mark(label: str, match: str) -> str:
        if answer_str is None:
            return label
        if match in {"yes", "no"}:
            return f"{label}✔" if answer_str == match else label
        return f"{label}✔" if str(answer) == match else label

    comment_label = "💬✔" if comment else "💬"
    photo_label = "📷✔" if photo else "📷"

    rows: list[list[InlineKeyboardButton]] = []

    if qtype in _YESNO_TYPES:
        rows.append([
            InlineKeyboardButton(text=mark("✅", "yes"), callback_data=f"block_answer:{qid}:yes"),
            InlineKeyboardButton(text=mark("❌", "no"), callback_data=f"block_answer:{qid}:no"),
            InlineKeyboardButton(text=comment_label, callback_data=f"block_comment:{qid}"),
            InlineKeyboardButton(text=photo_label, callback_data=f"block_photo:{qid}"),
        ])
    elif qtype in _SCALE_TYPES:
        rows.append([
            InlineKeyboardButton(text=mark(str(i), str(i)), callback_data=f"block_answer:{qid}:{i}")
            for i in range(1, 6)
        ])
        rows.append([
            InlineKeyboardButton(text=comment_label, callback_data=f"block_comment:{qid}"),
            InlineKeyboardButton(text=photo_label, callback_data=f"block_photo:{qid}"),
        ])
    else:
        answer_label = "✍️✔" if answer not in (None, "") else "✍️"
        rows.append([
            InlineKeyboardButton(text=answer_label, callback_data=f"block_answer:{qid}:text"),
            InlineKeyboardButton(text=comment_label, callback_data=f"block_comment:{qid}"),
            InlineKeyboardButton(text=photo_label, callback_data=f"block_photo:{qid}"),
        ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_block_nav_keyboard(index: int, total: int) -> InlineKeyboardMarkup:
    prev_cb = "block_nav:prev" if index > 0 else "block_nav:noop_prev"
    next_cb = "block_nav:next" if index < total - 1 else "block_nav:noop_next"
    nav_row = [
        InlineKeyboardButton(text="⬅️", callback_data=prev_cb),
        InlineKeyboardButton(text=f"{index + 1}/{total}", callback_data="block_nav:noop_info"),
        InlineKeyboardButton(text="➡️", callback_data=next_cb),
    ]
    rows = [
        nav_row,
        [InlineKeyboardButton(text="✅ Завершить", callback_data="block_finish")],
        [InlineKeyboardButton(text="🚪 Выйти", callback_data="exit_attempt")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _delete_block_question_messages(bot: Bot, chat_id: int, data: dict) -> None:
    raw = data.get("block_question_messages") or {}
    if isinstance(raw, dict):
        message_ids = list(raw.values())
    elif isinstance(raw, list):
        message_ids = raw
    else:
        message_ids = []

    for msg_id in message_ids:
        if not msg_id:
            continue
        try:
            await bot.delete_message(chat_id, msg_id)
        except Exception:
            pass


async def _delete_block_nav_message(bot: Bot, chat_id: int, data: dict) -> None:
    msg_id = data.get("block_nav_message_id")
    if not msg_id:
        return

    try:
        await bot.delete_message(chat_id, msg_id)
    except Exception:
        pass


async def _render_block(base_message: types.Message, state: FSMContext, target_index: int) -> None:
    data = await state.get_data()
    sections = data.get("block_sections") or []
    if not sections:
        await base_message.answer("Нет доступных блоков для этого чек-листа.")
        return

    total = len(sections)
    index = max(0, min(target_index, total - 1))
    section = sections[index]

    bot = base_message.bot
    chat_id = base_message.chat.id

    await _delete_block_nav_message(bot, chat_id, data)
    await _delete_block_question_messages(bot, chat_id, data)

    header_lines = [
        f"📂 Блок {index + 1} из {total}",
        f"<b>{_escape(section.get('title') or 'Без раздела')}</b>",
    ]
    count = len(section.get("items") or [])
    header_lines.append(f"Всего вопросов: {count}")
    header_text = "\n".join(header_lines)
    keyboard = _build_block_nav_keyboard(index, total)

    header_msg: types.Message | None = None
    header_id = data.get("block_header_message_id")

    if header_id:
        try:
            header_msg = await bot.edit_message_text(
                chat_id=chat_id,
                message_id=header_id,
                text=header_text,
                reply_markup=None,
                parse_mode="HTML",
            )
        except TelegramBadRequest:
            try:
                header_msg = await bot.send_message(
                    chat_id,
                    header_text,
                    parse_mode="HTML",
                )
            except TelegramBadRequest:
                header_msg = await base_message.answer(
                    header_text,
                    parse_mode="HTML",
                )
    else:
        try:
            header_msg = await base_message.edit_text(
                header_text,
                reply_markup=None,
                parse_mode="HTML",
            )
        except TelegramBadRequest:
            header_msg = await base_message.answer(
                header_text,
                parse_mode="HTML",
            )
            try:
                await _safe_delete(base_message)
            except Exception:
                pass

    if header_msg is None:
        header_msg = await base_message.answer(
            header_text,
            parse_mode="HTML",
        )
        header_id = header_msg.message_id
    else:
        header_id = header_msg.message_id

    answers_map = _normalize_answers_map(data.get("answers_map"))
    question_messages: dict[str, int] = {}

    for question in section.get("items", []):
        qid = question.get("id")
        if qid is None:
            continue
        draft = answers_map.setdefault(qid, {"answer": None, "comment": None, "photo_path": None})
        text = _question_text(question, draft)
        kb = _build_block_question_keyboard(question, qid, draft)
        sent = await header_msg.answer(text, reply_markup=kb, parse_mode="HTML")
        question_messages[str(qid)] = sent.message_id

    try:
        nav_msg = await header_msg.answer(
            "Навигация по блокам:",
            reply_markup=keyboard,
        )
        nav_id = nav_msg.message_id
    except TelegramBadRequest:
        nav_id = None

    await state.update_data(
        block_index=index,
        block_header_message_id=header_id,
        block_nav_message_id=nav_id,
        block_question_messages=question_messages,
        answers_map=answers_map,
        active_question_id=None,
        return_state=None,
    )


async def _refresh_block_question(message: types.Message, state: FSMContext, qid: int) -> None:
    data = await state.get_data()
    _, question = _resolve_question(data, qid)
    if not question:
        return

    answers_map = _normalize_answers_map(data.get("answers_map"))
    draft = answers_map.setdefault(qid, {"answer": None, "comment": None, "photo_path": None})

    mapping = data.get("block_question_messages") or {}
    if isinstance(mapping, dict):
        msg_id = mapping.get(str(qid)) or mapping.get(qid)
    else:
        msg_id = None

    if not msg_id:
        msg_id = getattr(message, "message_id", None)

    if not msg_id:
        return

    kb = _build_block_question_keyboard(question, qid, draft)
    text = _question_text(question, draft)

    try:
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=msg_id,
            text=text,
            reply_markup=kb,
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        try:
            await message.bot.edit_message_reply_markup(
                chat_id=message.chat.id,
                message_id=msg_id,
                reply_markup=kb,
            )
        except TelegramBadRequest:
            pass

    await state.update_data(answers_map=answers_map, active_question_id=None, return_state=None)


async def _finalize_attempt(message: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    await _clear_exit_confirmation(message.bot, message.chat.id, data, state)
    questions = data.get("questions") or []
    answers_map = _normalize_answers_map(data.get("answers_map"))
    attempt_id = data.get("attempt_id")
    selected_department = data.get("selected_department")

    attempt_data = None
    if attempt_id:
        final_attempt_id = await asyncio.to_thread(checklists_service.finish, attempt_id)
        if final_attempt_id:
            attempt_id = final_attempt_id
            try:
                attempt_data = await asyncio.to_thread(get_attempt_data, final_attempt_id)
            except Exception as exc:
                logger.warning("[CHECKLIST] get_attempt_data failed for attempt_id=%s: %s", final_attempt_id, exc)
        else:
            attempt_id = None

    await message.answer("✅ Чек-лист завершён. Спасибо!")

    if attempt_data and selected_department:
        attempt_data.department = selected_department

    info_lines = []
    if attempt_data:
        info_lines.append(f"📋 <b>{_escape(attempt_data.checklist_name)}</b>")
        info_lines.append(f"Дата: {attempt_data.submitted_at:%d.%m.%Y %H:%M}")
        if attempt_data.department:
            info_lines.append(f"Подразделение: {_escape(attempt_data.department)}")
        result_line = format_attempt_result(attempt_data)
        if attempt_data.is_scored and result_line:
            info_lines.append(f"Результат: {_escape(result_line)}")
    else:
        if selected_department:
            info_lines.append(f"Подразделение: {_escape(selected_department)}")
        info_lines.append("Результаты доступны ниже.")

    if info_lines:
        await message.answer("\n".join(info_lines), parse_mode="HTML")

    summary_text = _answers_summary_text(questions, answers_map, attempt_data=attempt_data)

    keyboard_rows = []
    if attempt_id:
        keyboard_rows.append([
            InlineKeyboardButton(text="📄 PDF", callback_data=f"completed_pdf:{attempt_id}:0"),
            InlineKeyboardButton(text="📊 Excel", callback_data=f"completed_excel:{attempt_id}:0"),
        ])
    keyboard_rows.append([InlineKeyboardButton(text="⬅️ В меню", callback_data="checklist_continue")])

    summary_kb = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    summary_msg = await message.answer(summary_text, parse_mode="HTML", reply_markup=summary_kb)

    recent_departments = data.get("recent_departments") or {}
    if attempt_id and selected_department:
        recent_departments[str(attempt_id)] = selected_department

    await state.update_data(
        next_actions_msg_id=summary_msg.message_id,
        attempt_data=attempt_data,
        recent_departments=recent_departments,
        pending_text=None,
        pending_text_msg_id=None,
        q_msg_id=None,
        block_sections=None,
        block_question_messages={},
        block_header_message_id=None,
        block_nav_message_id=None,
        block_index=None,
        mode=None,
        active_question_id=None,
        return_state=None,
        exit_confirm_message_id=None,
        attempt_id=attempt_id,
        resume_attempt_id=None,
        resume_prompt_message_id=None,
        resume_answered_count=None,
    )
    await state.set_state(Form.show_checklists)




@router.callback_query(F.data == "exit_attempt", Form.answering_question)
@router.callback_query(F.data == "exit_attempt", Form.answering_block)
@router.callback_query(F.data == "exit_attempt", Form.manual_text_answer)
@router.callback_query(F.data == "exit_attempt", Form.adding_comment)
@router.callback_query(F.data == "exit_attempt", Form.adding_photo)
async def handle_exit_attempt(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    attempt_id = data.get("attempt_id")
    if not attempt_id:
        await callback.answer("Нет активной попытки.", show_alert=True)
        return

    await callback.answer("Вы уверены? Прогресс будет потерян.", show_alert=True)

    await _clear_exit_confirmation(callback.message.bot, callback.message.chat.id, data, state)

    confirm_msg = await callback.message.answer(
        "❓ Выйти из прохождения чек-листа?",
        reply_markup=_build_exit_confirmation_keyboard(),
    )
    await state.update_data(exit_confirm_message_id=confirm_msg.message_id)


@router.callback_query(F.data == "exit_confirm", Form.answering_question)
@router.callback_query(F.data == "exit_confirm", Form.answering_block)
@router.callback_query(F.data == "exit_confirm", Form.manual_text_answer)
@router.callback_query(F.data == "exit_confirm", Form.adding_comment)
@router.callback_query(F.data == "exit_confirm", Form.adding_photo)
async def handle_exit_confirm(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer("Выход выполнен.")
    await _abort_attempt(callback.message, state)


@router.callback_query(F.data == "exit_cancel", Form.answering_question)
@router.callback_query(F.data == "exit_cancel", Form.answering_block)
@router.callback_query(F.data == "exit_cancel", Form.manual_text_answer)
@router.callback_query(F.data == "exit_cancel", Form.adding_comment)
@router.callback_query(F.data == "exit_cancel", Form.adding_photo)
async def handle_exit_cancel(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await _clear_exit_confirmation(callback.message.bot, callback.message.chat.id, data, state)
    await callback.answer("Продолжаем заполнение.")


@router.callback_query(F.data.startswith("block_answer:"), Form.answering_block)
async def handle_block_answer(callback: types.CallbackQuery, state: FSMContext):
    try:
        _, qid_raw, value = callback.data.split(":", 2)
    except ValueError:
        await callback.answer()
        return

    try:
        qid = int(qid_raw)
    except ValueError:
        await callback.answer()
        return

    data = await state.get_data()
    _, question = _resolve_question(data, qid)
    if not question:
        await callback.answer("Вопрос не найден", show_alert=True)
        return

    if value == "text":
        await state.update_data(active_question_id=qid, return_state=Form.answering_block)
        await state.set_state(Form.manual_text_answer)
        try:
            await callback.message.edit_text(
                "✍️ Введите ваш ответ текстом:",
                reply_markup=build_submode_keyboard(),
            )
        except TelegramBadRequest:
            await callback.message.answer(
                "✍️ Введите ваш ответ текстом:",
                reply_markup=build_submode_keyboard(),
            )
        await callback.answer()
        return

    answers_map = _normalize_answers_map(data.get("answers_map"))
    draft = answers_map.setdefault(qid, {"answer": None, "comment": None, "photo_path": None})
    draft["answer"] = value
    answers_map[qid] = draft

    await state.update_data(answers_map=answers_map, active_question_id=None, return_state=None)

    attempt_id = data.get("attempt_id")
    if attempt_id:
        await asyncio.to_thread(checklists_service.save_answer, attempt_id, qid, value)

    await _refresh_block_question(callback.message, state, qid)
    await state.set_state(Form.answering_block)
    await callback.answer("Ответ сохранён")


@router.callback_query(F.data.startswith("block_comment:"), Form.answering_block)
async def handle_block_comment(callback: types.CallbackQuery, state: FSMContext):
    try:
        qid = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer()
        return

    data = await state.get_data()
    answers_map = _normalize_answers_map(data.get("answers_map"))
    answers_map.setdefault(qid, {"answer": None, "comment": None, "photo_path": None})
    await state.update_data(
        answers_map=answers_map,
        active_question_id=qid,
        return_state=Form.answering_block,
        submode="comment",
    )

    await state.set_state(Form.adding_comment)
    try:
        await callback.message.edit_text(
            "💬 Введите ваш комментарий:",
            reply_markup=build_submode_keyboard(),
        )
    except TelegramBadRequest:
        await callback.message.answer(
            "💬 Введите ваш комментарий:",
            reply_markup=build_submode_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("block_photo:"), Form.answering_block)
async def handle_block_photo(callback: types.CallbackQuery, state: FSMContext):
    try:
        qid = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer()
        return

    data = await state.get_data()
    answers_map = _normalize_answers_map(data.get("answers_map"))
    answers_map.setdefault(qid, {"answer": None, "comment": None, "photo_path": None})
    await state.update_data(
        answers_map=answers_map,
        active_question_id=qid,
        return_state=Form.answering_block,
        submode="photo",
    )

    await state.set_state(Form.adding_photo)
    try:
        await callback.message.edit_text(
            "📷 Отправьте фото:",
            reply_markup=build_submode_keyboard(),
        )
    except TelegramBadRequest:
        await callback.message.answer(
            "📷 Отправьте фото:",
            reply_markup=build_submode_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("block_nav:"), Form.answering_block)
async def handle_block_navigation(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(":", 1)[1]

    if action.startswith("noop") or action == "noop_info":
        if action == "noop_prev":
            await callback.answer("Это первый блок", show_alert=True)
        elif action == "noop_next":
            await callback.answer("Это последний блок", show_alert=True)
        else:
            await callback.answer()
        return

    data = await state.get_data()
    current = data.get("block_index") or 0
    sections = data.get("block_sections") or []

    if action == "prev":
        target = current - 1
        if target < 0:
            await callback.answer("Это первый блок", show_alert=True)
            return
    elif action == "next":
        target = current + 1
        if target >= len(sections):
            await callback.answer("Это последний блок", show_alert=True)
            return
    else:
        await callback.answer()
        return

    await _render_block(callback.message, state, target)
    await callback.answer()


@router.callback_query(F.data == "block_finish", Form.answering_block)
async def handle_block_finish(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    questions = data.get("questions") or []
    answers_map = _normalize_answers_map(data.get("answers_map"))

    for idx, question in enumerate(questions, start=1):
        qid = question.get("id")
        if qid is None:
            continue
        draft = answers_map.get(qid, {})
        answer = draft.get("answer")
        has_answer = answer is not None
        if isinstance(answer, str):
            has_answer = bool(answer.strip())

        title = (question.get("text") or question.get("question_text") or "").strip() or f"Вопрос #{idx}"

        if not has_answer:
            await callback.answer(f"Ответьте на вопрос: {title}", show_alert=True)
            return

        comment = draft.get("comment")
        if question.get("require_comment") and not (comment and str(comment).strip()):
            await callback.answer(f"Добавьте обязательный комментарий к вопросу: {title}", show_alert=True)
            return

        if question.get("require_photo") and not draft.get("photo_path"):
            await callback.answer(f"Добавьте обязательное фото к вопросу: {title}", show_alert=True)
            return

    await _delete_block_question_messages(callback.message.bot, callback.message.chat.id, data)

    header_msg_id = data.get("block_header_message_id")
    if header_msg_id:
        try:
            await callback.message.bot.delete_message(callback.message.chat.id, header_msg_id)
        except Exception:
            pass

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await _safe_delete(callback.message)

    await _finalize_attempt(callback.message, state)
    await callback.answer()


def _build_text_choice_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 Ответ", callback_data="text_choice:answer"),
            InlineKeyboardButton(text="💬 Комментарий", callback_data="text_choice:comment"),
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="text_choice:cancel")],
    ])


def _build_resume_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Продолжить", callback_data="resume:continue")],
        [InlineKeyboardButton(text="🆕 Начать заново", callback_data="resume:new")],
    ])


def _build_exit_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Выйти", callback_data="exit_confirm")],
        [InlineKeyboardButton(text="↩️ Остаться", callback_data="exit_cancel")],
    ])


async def _clear_exit_confirmation(bot: Bot, chat_id: int, data: dict, state: FSMContext) -> None:
    msg_id = data.get("exit_confirm_message_id")
    if not msg_id:
        return
    try:
        await bot.delete_message(chat_id, msg_id)
    except Exception:
        pass
    await state.update_data(exit_confirm_message_id=None)


async def _abort_attempt(message: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    bot = message.bot
    chat_id = message.chat.id

    await _clear_exit_confirmation(bot, chat_id, data, state)

    attempt_id = data.get("attempt_id")
    if attempt_id:
        await asyncio.to_thread(checklists_service.discard, attempt_id)

    q_msg_id = data.get("q_msg_id")
    if q_msg_id:
        try:
            await bot.delete_message(chat_id, q_msg_id)
        except Exception:
            pass

    pending_text_msg_id = data.get("pending_text_msg_id")
    if pending_text_msg_id:
        try:
            await bot.delete_message(chat_id, pending_text_msg_id)
        except Exception:
            pass

    next_actions_msg_id = data.get("next_actions_msg_id")
    if next_actions_msg_id:
        try:
            await bot.delete_message(chat_id, next_actions_msg_id)
        except Exception:
            pass

    await _delete_block_question_messages(bot, chat_id, data)
    await _delete_block_nav_message(bot, chat_id, data)

    header_id = data.get("block_header_message_id")
    if header_id:
        try:
            await bot.delete_message(chat_id, header_id)
        except Exception:
            pass

    await state.update_data(
        attempt_id=None,
        attempt_data=None,
        answers_map={},
        current=None,
        pending_text=None,
        pending_text_msg_id=None,
        next_actions_msg_id=None,
        q_msg_id=None,
        block_sections=None,
        block_question_messages={},
        block_header_message_id=None,
        block_nav_message_id=None,
        block_index=None,
        mode=None,
        active_question_id=None,
        return_state=None,
        exit_confirm_message_id=None,
        checklist_id=None,
        questions=None,
        question_map=None,
        pending_checklist_id=None,
        selected_department=None,
        resume_attempt_id=None,
        resume_prompt_message_id=None,
        resume_answered_count=None,
    )

    await state.set_state(Form.show_checklists)

    await message.answer("❌ Прохождение отменено. Прогресс удалён.")

    user_id = data.get("user_id")
    if user_id:
        checklists = await asyncio.to_thread(auth_service.get_user_checklists, user_id)
        if checklists:
            await state.update_data(
                checklists_map={str(c["id"]): c["name"] for c in checklists},
            )
            await message.answer("Выберите чек-лист:", reply_markup=get_checklists_keyboard(checklists))
        else:
            await message.answer("У вас пока нет доступных чек-листов.")
    else:
        await send_main_menu(message)

async def _prompt_department_choice(message: types.Message, state: FSMContext):
    data = await state.get_data()
    options = data.get("department_options") or []
    checklist_name = data.get("checklist_name") or "чек-лист"
    if options:
        kb = _build_department_keyboard(options)
        sent = await message.answer(
            f"🏢 Выберите объект/подразделение для «{_escape(checklist_name)}»:",
            reply_markup=kb,
            parse_mode="HTML",
        )
        await state.update_data(department_prompt_message_id=sent.message_id, checklist_start_dt=None)
        await state.set_state(Form.selecting_department)
    else:
        sent = await message.answer("🏢 Укажите название объекта (введите текст):")
        await state.update_data(department_prompt_message_id=sent.message_id, checklist_start_dt=None)
        await state.set_state(Form.entering_custom_department)


async def _prompt_mode_selection(message: types.Message, state: FSMContext, department: str):
    data = await state.get_data()
    checklist_name = data.get("checklist_name") or "чек-лист"

    tz_msk = ZoneInfo("Europe/Moscow")
    started_at_raw = data.get("checklist_start_dt")
    started_at = None

    if started_at_raw:
        try:
            parsed = datetime.fromisoformat(started_at_raw)
        except ValueError:
            parsed = None
        if parsed is not None:
            if parsed.tzinfo is None:
                started_at = parsed.replace(tzinfo=tz_msk)
            else:
                started_at = parsed.astimezone(tz_msk)

    if started_at is None:
        started_at = datetime.now(tz_msk)

    started_msk = started_at.astimezone(tz_msk)
    start_iso = started_msk.isoformat()
    started_str = started_msk.strftime("%d.%m.%Y %H:%M")

    text = (
        f"🏢 Выбранный объект: <b>{_escape(department)}</b>\n"
        f"📋 Чек-лист: <b>{_escape(checklist_name)}</b>\n"
        f"🕒 Начало заполнения: {started_str} (МСК)\n\n"
        "Выберите режим прохождения:"
    )

    keyboard = _build_mode_keyboard()
    updated_message: types.Message | None = None

    try:
        updated_message = await message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        updated_message = None

    if updated_message is None:
        prompt_msg_id = data.get("department_prompt_message_id")
        if prompt_msg_id:
            try:
                updated_message = await message.bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=prompt_msg_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
            except TelegramBadRequest:
                updated_message = None

    if updated_message is None:
        updated_message = await message.answer(
            text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )

    await state.update_data(
        department_prompt_message_id=updated_message.message_id,
        checklist_start_dt=start_iso,
    )
    await state.set_state(Form.choosing_checklist_mode)


@router.callback_query(F.data.startswith("dept_select:"), Form.selecting_department)
async def handle_department_choice(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    options = data.get("department_options") or []
    try:
        idx = int(callback.data.split(":")[1])
    except Exception:
        await callback.answer("Не удалось определить подразделение", show_alert=True)
        return
    if idx < 0 or idx >= len(options):
        await callback.answer("Не удалось определить подразделение", show_alert=True)
        return
    selected = options[idx]
    await state.update_data(
        selected_department=selected,
        checklist_start_dt=None,
        department_prompt_message_id=callback.message.message_id,
    )
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await _prompt_mode_selection(callback.message, state, selected)
    await callback.answer()


@router.callback_query(F.data == "dept_other", Form.selecting_department)
async def handle_department_other(callback: types.CallbackQuery, state: FSMContext):
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer("Введите название объекта/подразделения текстом:")
    await state.set_state(Form.entering_custom_department)
    await callback.answer()


@router.message(Form.entering_custom_department)
async def handle_custom_department(message: types.Message, state: FSMContext):
    title = (message.text or "").strip()
    if not title:
        await message.answer("Название не может быть пустым. Попробуйте снова.")
        return

    await state.update_data(selected_department=title, checklist_start_dt=None)
    await _safe_delete(message)
    await _prompt_mode_selection(message, state, title)


@router.callback_query(F.data == "mode:back", Form.choosing_checklist_mode)
async def handle_mode_back(callback: types.CallbackQuery, state: FSMContext):
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await state.update_data(
        selected_department=None,
        checklist_start_dt=None,
        department_prompt_message_id=None,
    )
    await _prompt_department_choice(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "mode:full", Form.choosing_checklist_mode)
async def handle_mode_show_full(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    questions = data.get("questions") or []
    if not questions:
        await callback.answer("Нет вопросов для отображения", show_alert=True)
        return

    sections_payload = []
    for section in group_questions_by_section(questions):
        questions_texts = []
        for q in section["items"]:
            text = (q.get("text") or q.get("question_text") or "").strip()
            if not text:
                text = f"Вопрос #{len(questions_texts) + 1}"
            questions_texts.append(text)
        sections_payload.append({
            "title": section["title"],
            "questions": questions_texts,
        })

    if not sections_payload:
        await callback.answer("Нет вопросов для отображения", show_alert=True)
        return

    await state.update_data(
        full_preview_sections=sections_payload,
        full_preview_index=0,
    )

    text = _format_full_preview_page(sections_payload, 0)
    keyboard = _build_full_preview_keyboard(0, len(sections_payload))

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("mode:full_page:"), Form.choosing_checklist_mode)
async def handle_mode_full_page(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":", 2)
    if len(parts) < 3:
        await callback.answer()
        return

    target_raw = parts[2]
    if target_raw == "noop":
        await callback.answer()
        return

    try:
        target_index = int(target_raw)
    except ValueError:
        await callback.answer()
        return

    data = await state.get_data()
    sections = data.get("full_preview_sections") or []
    if not sections:
        await callback.answer("Нет данных для предпросмотра", show_alert=True)
        return

    total = len(sections)
    target_index = max(0, min(target_index, total - 1))
    current_index = data.get("full_preview_index", 0)
    if target_index == current_index:
        await callback.answer()
        return

    text = _format_full_preview_page(sections, target_index)
    keyboard = _build_full_preview_keyboard(target_index, total)

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await state.update_data(full_preview_index=target_index)
    await callback.answer()


@router.callback_query(F.data == "mode:full_back", Form.choosing_checklist_mode)
async def handle_mode_full_back(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    department = data.get("selected_department")

    await state.update_data(full_preview_sections=None, full_preview_index=None)
    await _safe_delete(callback.message)

    if department:
        await _prompt_mode_selection(callback.message, state, department)
    else:
        await _prompt_department_choice(callback.message, state)

    await callback.answer()


@router.callback_query(F.data == "mode:blocks", Form.choosing_checklist_mode)
async def handle_mode_blocks(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id")
    checklist_id = data.get("pending_checklist_id")
    questions = data.get("questions") or []
    selected_department = data.get("selected_department")

    if not (user_id and checklist_id and questions):
        await callback.answer("Не удалось подготовить прохождение по блокам", show_alert=True)
        return

    attempt_id = await asyncio.to_thread(
        checklists_service.start_attempt,
        user_id,
        checklist_id,
    )
    answers_map = await asyncio.to_thread(
        checklists_service.get_attempt_answers,
        attempt_id,
    ) or {}
    answers_map = _normalize_answers_map(answers_map)

    sections = group_questions_by_section(questions)
    question_map = data.get("question_map") or {
        q.get("id"): q for q in questions if q.get("id") is not None
    }

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    block_start_index = _first_unanswered_block_index(sections, answers_map)

    await state.update_data(
        checklist_id=checklist_id,
        attempt_id=attempt_id,
        answers_map=answers_map,
        selected_department=selected_department,
        attempt_data=None,
        mode="blocks",
        block_sections=sections,
        block_index=block_start_index,
        block_question_messages={},
        block_header_message_id=None,
        block_nav_message_id=None,
        active_question_id=None,
        return_state=None,
        question_map=question_map,
        recent_departments=data.get("recent_departments", {}),
        exit_confirm_message_id=None,
        resume_attempt_id=None,
        resume_prompt_message_id=None,
        resume_answered_count=None,
    )

    if selected_department:
        await asyncio.to_thread(
            checklists_service.set_draft_department,
            attempt_id,
            selected_department,
        )

    await state.set_state(Form.answering_block)
    await _render_block(callback.message, state, block_start_index)
    await callback.answer()


@router.callback_query(F.data == "mode:start", Form.choosing_checklist_mode)
async def handle_mode_start(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id")
    checklist_id = data.get("pending_checklist_id")
    questions = data.get("questions")
    selected_department = data.get("selected_department")

    if not (user_id and checklist_id and questions):
        await callback.answer("Не удалось начать прохождение", show_alert=True)
        return

    attempt_id = await asyncio.to_thread(
        checklists_service.start_attempt,
        user_id,
        checklist_id,
    )
    answers_map = await asyncio.to_thread(
        checklists_service.get_attempt_answers,
        attempt_id,
    ) or {}
    answers_map = _normalize_answers_map(answers_map)

    first_unanswered = _first_unanswered_index(questions, answers_map)

    await state.update_data(
        checklist_id=checklist_id,
        attempt_id=attempt_id,
        answers_map=answers_map,
        current=first_unanswered,
        selected_department=selected_department,
        attempt_data=None,
        recent_departments=data.get("recent_departments", {}),
        full_preview_sections=None,
        full_preview_index=None,
        mode="sequence",
        active_question_id=None,
        return_state=None,
        exit_confirm_message_id=None,
        resume_attempt_id=None,
        resume_prompt_message_id=None,
        resume_answered_count=None,
    )

    if selected_department:
        await asyncio.to_thread(
            checklists_service.set_draft_department,
            attempt_id,
            selected_department,
        )

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await state.set_state(Form.answering_question)
    await callback.message.answer("📝 Начинаем чек-лист...", reply_markup=ReplyKeyboardRemove())
    await ask_next_question(callback.message, state)
    await callback.answer()


async def ask_next_question(message: types.Message, state: FSMContext):
    data = await state.get_data()
    questions = data["questions"]
    current = data["current"]
    answers_map = _normalize_answers_map(data.get("answers_map"))
    q_msg_id = data.get("q_msg_id")

    # завершение
    if current >= len(questions):
        await _finalize_attempt(message, state)
        return


    # показать/перерисовать текущий вопрос
    question = questions[current]
    qid = question["id"]
    draft = answers_map.setdefault(qid, {"answer": None, "comment": None, "photo_path": None})
    await state.update_data(answers_map=answers_map, active_question_id=None, return_state=None)

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
            parse_mode="HTML"
        )
        await message.bot.edit_message_reply_markup(
            chat_id=message.chat.id,
            message_id=q_msg_id,
            reply_markup=kb
        )
    else:
        sent = await message.answer(text, reply_markup=kb, parse_mode="HTML")
        await state.update_data(q_msg_id=sent.message_id)




@router.callback_query(F.data.startswith("answer:"), Form.answering_question)
async def handle_answer(callback: types.CallbackQuery, state: FSMContext):
    value = callback.data.split(":")[1]  # 'yes'/'no' | '1'..'5' | 'text'
    data = await state.get_data()
    questions = data["questions"]
    current = data["current"]
    answers_map = _normalize_answers_map(data.get("answers_map"))
    q_msg_id = data.get("q_msg_id")
    question = questions[current]
    attempt_id = data.get("attempt_id")

    question = questions[current]
    qid = question["id"]

    # Если выбран текстовый ответ — переходим в режим ввода, редактируя то же сообщение
    if value == "text":
        await state.update_data(active_question_id=qid, return_state=Form.answering_question)
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
    prev_answer = draft.get("answer")
    draft["answer"] = value
    answers_map[qid] = draft
    await state.update_data(answers_map=answers_map)

    if attempt_id:
        await asyncio.to_thread(checklists_service.save_answer, attempt_id, qid, value)

    kb = build_question_keyboard(question["type"], current, selected=value)
    text = _question_text(question, draft)

    try:
        await callback.bot.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=q_msg_id or callback.message.message_id,
            text=text,
            reply_markup=kb,
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        # если текст не изменился — обновим хотя бы клавиатуру
        try:
            await callback.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=q_msg_id or callback.message.message_id,
                reply_markup=kb
            )
        except TelegramBadRequest:
            pass

    await callback.answer("Ответ записан. Можно добавить комментарий/фото или нажать «Далее».")

# helper — тихо удаляем любое сообщение
async def _safe_delete(msg: types.Message):
    try:
        await msg.delete()
    except Exception:
        pass



async def _save_text_answer(message: types.Message, state: FSMContext, text_answer: str, *, delete_message: bool = True):
    data = await state.get_data()
    qid, question = _resolve_question(data, data.get("active_question_id"))
    if not qid or not question:
        return

    answers_map = _normalize_answers_map(data.get("answers_map"))
    answers_map.setdefault(qid, {"answer": None, "comment": None, "photo_path": None})["answer"] = text_answer
    await state.update_data(answers_map=answers_map)

    attempt_id = data.get("attempt_id")
    if attempt_id:
        await asyncio.to_thread(checklists_service.save_answer, attempt_id, qid, text_answer)

    if delete_message:
        await _safe_delete(message)

    return_state = data.get("return_state") or Form.answering_question
    await state.update_data(active_question_id=None, return_state=None)

    if return_state == Form.answering_block:
        await state.set_state(Form.answering_block)
        await _refresh_block_question(message, state, qid)
    else:
        await state.set_state(Form.answering_question)
        await ask_next_question(message, state)


async def _save_comment_text(message: types.Message, state: FSMContext, comment_text: str, *, delete_message: bool = True):
    data = await state.get_data()
    qid, question = _resolve_question(data, data.get("active_question_id"))
    if not qid or not question:
        return

    answers_map = _normalize_answers_map(data.get("answers_map"))
    answers_map.setdefault(qid, {"answer": None, "comment": None, "photo_path": None})["comment"] = comment_text
    await state.update_data(answers_map=answers_map)

    attempt_id = data.get("attempt_id")
    if attempt_id:
        await asyncio.to_thread(checklists_service.save_comment, attempt_id, qid, comment_text)

    if delete_message:
        await _safe_delete(message)

    return_state = data.get("return_state") or Form.answering_question
    await state.update_data(active_question_id=None, return_state=None)

    if return_state == Form.answering_block:
        await state.set_state(Form.answering_block)
        await _refresh_block_question(message, state, qid)
    else:
        await state.set_state(Form.answering_question)
        await ask_next_question(message, state)


@router.message(Form.manual_text_answer)
async def handle_manual_text_answer(message: types.Message, state: FSMContext):
    text_answer = (message.text or "").strip()
    if not text_answer:
        await message.answer("Ответ не может быть пустым. Попробуйте снова.")
        return
    await _save_text_answer(message, state, text_answer)



@router.callback_query(F.data.startswith("comment:"), Form.answering_question)
async def handle_comment_button(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    q_msg_id = data.get("q_msg_id")
    questions = data.get("questions") or []
    current = data.get("current")
    qid = None
    if current is not None and 0 <= current < len(questions):
        qid = questions[current]["id"]

    await state.set_state(Form.adding_comment)
    await state.update_data(
        submode="comment",
        active_question_id=qid,
        return_state=Form.answering_question,
    )

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
    comment_text = (message.text or "").strip()
    if not comment_text:
        await message.answer("Комментарий не может быть пустым. Попробуйте снова.")
        return
    await _save_comment_text(message, state, comment_text)

async def _attach_photo_to_current_question(message: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    answers_map = _normalize_answers_map(data.get("answers_map"))
    attempt_id = data.get("attempt_id")

    if not message.photo:
        await message.answer("Пожалуйста, отправьте фото.")
        return

    qid, question = _resolve_question(data, data.get("active_question_id"))
    if not qid or not question:
        await message.answer("Не удалось определить вопрос для фото.")
        return

    file_id = message.photo[-1].file_id
    stored_path = await _store_photo_locally(message.bot, file_id, attempt_id, qid)
    photo_value = stored_path or file_id

    answers_map.setdefault(qid, {"answer": None, "comment": None, "photo_path": None})["photo_path"] = photo_value
    await state.update_data(answers_map=answers_map)

    if attempt_id:
        await asyncio.to_thread(checklists_service.save_photo, attempt_id, qid, photo_value)

    await _safe_delete(message)

    return_state = data.get("return_state") or Form.answering_question
    await state.update_data(active_question_id=None, return_state=None)

    if return_state == Form.answering_block:
        await state.set_state(Form.answering_block)
        await _refresh_block_question(message, state, qid)
    else:
        await state.set_state(Form.answering_question)
        await ask_next_question(message, state)


@router.message(F.photo, Form.answering_question)
async def handle_direct_photo(message: types.Message, state: FSMContext):
    await _attach_photo_to_current_question(message, state)


@router.message(Form.answering_question, F.text, ~F.text.in_(_RESERVED_TEXT_COMMANDS))
async def handle_direct_text(message: types.Message, state: FSMContext):

    text_value = (message.text or "").strip()
    if not text_value:
        await _safe_delete(message)
        return

    data = await state.get_data()
    questions = data.get("questions") or []
    current = data.get("current")
    if current is None or current >= len(questions):
        await _safe_delete(message)
        return

    question = questions[current]
    qtype = (question.get("type") or "").lower().strip()
    qid = question.get("id")
    await state.update_data(active_question_id=qid, return_state=Form.answering_question)

    if qtype in {"yesno", "yes_no", "boolean", "bool", "yn", "scale", "rating"}:
        await _save_comment_text(message, state, text_value)
        return

    await state.update_data(pending_text=text_value)
    await _safe_delete(message)
    prompt = await message.answer(
        "Принять этот текст как ответ или комментарий?",
        reply_markup=_build_text_choice_keyboard()
    )
    await state.update_data(pending_text_msg_id=prompt.message_id)
    await state.set_state(Form.text_decision)


@router.callback_query(F.data.startswith("photo:"), Form.answering_question)
async def handle_photo_button(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    q_msg_id = data.get("q_msg_id")
    questions = data.get("questions") or []
    current = data.get("current")
    qid = None
    if current is not None and 0 <= current < len(questions):
        qid = questions[current]["id"]
    await state.set_state(Form.adding_photo)
    await state.update_data(
        active_question_id=qid,
        return_state=Form.answering_question,
        submode="photo",
    )

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
    await _attach_photo_to_current_question(message, state)


@router.callback_query(F.data.startswith("text_choice:"), Form.text_decision)
async def handle_text_choice(callback: types.CallbackQuery, state: FSMContext):
    choice = callback.data.split(":", 1)[1]
    data = await state.get_data()
    text_value = data.get("pending_text")
    msg_id = data.get("pending_text_msg_id")

    if msg_id and msg_id != callback.message.message_id:
        try:
            await callback.bot.delete_message(callback.message.chat.id, msg_id)
        except Exception:
            pass

    await state.update_data(pending_text=None, pending_text_msg_id=None)

    if choice == "answer" and text_value:
        await _save_text_answer(callback.message, state, text_value)
        await callback.answer("Ответ сохранён")
    elif choice == "comment" and text_value:
        await _save_comment_text(callback.message, state, text_value)
        await callback.answer("Комментарий сохранён")
    else:
        await state.set_state(Form.answering_question)
        await _safe_delete(callback.message)
        await callback.answer("Отменено")


@router.callback_query(F.data == "back_to_question")
async def handle_back_to_question(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    return_state = data.get("return_state") or Form.answering_question
    qid = data.get("active_question_id")

    await state.update_data(active_question_id=None, return_state=None)

    if return_state == Form.answering_block and qid:
        await state.set_state(Form.answering_block)
        await _refresh_block_question(callback.message, state, qid)
    else:
        await state.set_state(Form.answering_question)
        await ask_next_question(callback.message, state)
    await callback.answer()

@router.callback_query(F.data == "continue_after_extra")
async def handle_continue_after_extra(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    questions = data["questions"]
    current = data["current"]
    answers_map = _normalize_answers_map(data.get("answers_map"))
    q_msg_id = data.get("q_msg_id")

    if current >= len(questions):
        await callback.answer("Все вопросы уже пройдены.", show_alert=True)
        return

    question = questions[current]

    # 1) Проверяем, что ответ есть
    qid = question["id"]
    has_answer = answers_map.get(qid, {}).get("answer") is not None
    if not has_answer:
        await callback.answer("Сначала выберите ответ на вопрос.", show_alert=True)
        return

    draft = answers_map.get(qid, {})
    comment = draft.get("comment")
    photo_path = draft.get("photo_path")

    if question.get("require_comment") and not (comment and str(comment).strip()):
        await callback.answer("Добавьте обязательный комментарий, это требование для вопроса.", show_alert=True)
        return

    if question.get("require_photo") and not photo_path:
        await callback.answer("Прикрепите обязательное фото, это требование для вопроса.", show_alert=True)
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

    # Если закончились вопросы, state уже переставлен на show_checklists; в этом случае отвечаем один раз
    try:
        await callback.answer()
    except TelegramBadRequest:
        pass

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
    answers_map = _normalize_answers_map(data.get("answers_map"))

    lines = ["🔍 <b>Подробные ответы:</b>"]
    for q in questions:
        d = answers_map.get(q["id"], {})
        ans = d.get("answer")
        comment = d.get("comment")
        photo = "есть" if d.get("photo_path") else "нет"
        ans_text = "—" if ans is None else _escape(str(ans))
        comment_text = "—" if not comment else _escape(str(comment))
        lines.append(
            f"— {_escape(str(q['text']))}: <b>{ans_text}</b> | 💬 {comment_text} | 📷 {photo}"
        )

    text = "\n".join(lines)

    await callback.message.answer(text, parse_mode="HTML")
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
    answers_map = _normalize_answers_map(data.get("answers_map"))

    attempt_data = data.get("attempt_data")
    text = _answers_summary_text(questions, answers_map, attempt_data=attempt_data)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_next_actions")],
    ])

    if msg_id:
        await callback.bot.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=msg_id,
            text=text,
            parse_mode="HTML"
        )
        await callback.bot.edit_message_reply_markup(
            chat_id=callback.message.chat.id,
            message_id=msg_id,
            reply_markup=kb
        )
    else:
        # запасной вариант, если msg_id потеряли
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)

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
    await send_main_menu(callback.message)
    await callback.answer()

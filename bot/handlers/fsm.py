"""Основные FSM-хэндлеры бота."""

import asyncio
import json
import logging
import os
import tempfile
import uuid
from urllib.parse import urlparse

import aiohttp
from aiogram import Router, types, F
from aiogram.exceptions import TelegramBadRequest, SkipHandler
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

from ..bot_logic import (
    get_checklists_for_user,
    get_completed_checklists_for_user,
    get_completed_answers_paginated,
    get_answer_report_data,
)
from ..export import export_attempt_to_files
from ..keyboards.inline import get_identity_confirmation_keyboard, get_checklists_keyboard
from ..keyboards.reply import authorized_keyboard
from ..report_data import get_attempt_data
from ..services.auth import AuthService
from ..states import Form
from ..utils.export_helpers import prepare_attempt_for_export
from ..utils.timezone import format_moscow, to_moscow


logger = logging.getLogger(__name__)

router = Router()
auth_service = AuthService()

# === Настройки медиа/фото для PDF ===
MEDIA_ROOT = os.getenv("MEDIA_ROOT", "media")
os.makedirs(MEDIA_ROOT, exist_ok=True)

_RESERVED_TEXT_COMMANDS = {
    "🏠 Домой",
    "🚪 Выйти",
    "✅ Доступные чек-листы",
    "📋 Пройденные чек-листы",
    "ℹ️ Обо мне",
}

async def _save_bytes_to_temp(data_bytes: bytes, suffix: str = ".jpg") -> str:
    tmp_name = f"{uuid.uuid4().hex}{suffix}"
    local_path = os.path.join(tempfile.gettempdir(), tmp_name)
    with open(local_path, "wb") as f:
        f.write(data_bytes)
    return local_path

def _try_extract_file_id(s: str) -> str | None:
    # file_id:XXXX → XXXX
    if s.startswith("file_id:"):
        return s.split("file_id:", 1)[1].strip() or None
    # JSON-строка с file_id
    if s and (s.lstrip().startswith("{") or s.lstrip().startswith("[")):
        try:
            obj = json.loads(s)
            if isinstance(obj, dict) and "file_id" in obj:
                return obj["file_id"]
            if isinstance(obj, list) and obj and isinstance(obj[0], dict) and "file_id" in obj[0]:
                return obj[0]["file_id"]
        except Exception:
            return None
    return None

def _is_url(s: str) -> bool:
    try:
        u = urlparse(s)
        return u.scheme in ("http", "https")
    except Exception:
        return False

def _is_url(s: str) -> bool:
    try:
        u = urlparse(s)
        return u.scheme in ("http", "https")
    except Exception:
        return False

def _try_extract_file_id(s: str) -> str | None:
    # file_id:XXXX → XXXX
    if s.startswith("file_id:"):
        return s.split("file_id:", 1)[1].strip() or None
    # JSON-строка с file_id
    t = s.lstrip()
    if t.startswith("{") or t.startswith("["):
        try:
            obj = json.loads(s)
            if isinstance(obj, dict) and "file_id" in obj:
                return obj["file_id"]
            if isinstance(obj, list) and obj and isinstance(obj[0], dict) and "file_id" in obj[0]:
                return obj[0]["file_id"]
        except Exception:
            return None
    return None

async def _save_bytes_to_temp(data_bytes: bytes, suffix: str = ".jpg") -> str:
    tmp_name = f"{uuid.uuid4().hex}{suffix}"
    local_path = os.path.join(tempfile.gettempdir(), tmp_name)
    with open(local_path, "wb") as f:
        f.write(data_bytes)
    return local_path

async def _hydrate_photos_for_attempt(data, bot):
    ok = miss = 0
    for row in data.answers:
        p = row.photo_path
        logger.debug("[PHOTO] raw value: %r", p)

        if not p:
            continue

        # 1) Абсолютный локальный путь
        if os.path.isabs(p) and os.path.exists(p):
            ok += 1
            continue

        # 2) Относительный путь в MEDIA_ROOT
        candidate = os.path.join(MEDIA_ROOT, p) if not os.path.isabs(p) else p
        if os.path.exists(candidate):
            row.photo_path = candidate
            ok += 1
            continue

        # 3) URL
        if _is_url(p):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(p) as resp:
                        if resp.status == 200:
                            content = await resp.read()
                            suffix = os.path.splitext(urlparse(p).path)[1] or ".jpg"
                            row.photo_path = await _save_bytes_to_temp(content, suffix=suffix)
                            ok += 1
                            continue
                        else:
                            logger.warning("[PHOTO] URL fetch failed %s: %s", resp.status, p)
            except Exception as e:
                logger.warning("[PHOTO] URL fetch error: %s", e)

        # 4) file_id (чистый, с префиксом, либо json)
        file_id = _try_extract_file_id(p) or p
        try:
            tg_file = await bot.get_file(file_id)
            tmp_name = f"{data.attempt_id}_{row.number}_{uuid.uuid4().hex}.jpg"
            local_path = os.path.join(tempfile.gettempdir(), tmp_name)
            # aiogram v3
            await bot.download(tg_file, destination=local_path)
            if os.path.exists(local_path):
                row.photo_path = local_path
                ok += 1
            else:
                row.photo_path = None
                miss += 1
        except TelegramBadRequest:
            row.photo_path = None
            miss += 1
        except Exception as e:
            logger.warning("[PHOTO] download error: %s", e)
            row.photo_path = None
            miss += 1

    logger.info("[PHOTO] localized: %s, missing: %s", ok, miss)




# 🚀 Нажал "Начать"
@router.callback_query(F.data == "start_checklist")
async def ask_login(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ваш логин:")
    await state.set_state(Form.entering_login)
    await callback.answer()


# ✍️ Вводит логин
@router.message(Form.entering_login)
async def ask_password(message: types.Message, state: FSMContext):
    await state.update_data(login=message.text.strip())
    await message.answer("Введите ваш пароль:")
    await state.set_state(Form.entering_password)


# 🔐 Вводит пароль → проверка
@router.message(Form.entering_password)
async def confirm_user(message: types.Message, state: FSMContext):
    await state.update_data(password=message.text.strip())
    data = await state.get_data()

    login = data.get("login", "").strip()
    password = data.get("password", "")

    user = await asyncio.to_thread(auth_service.authenticate, login, password)

    if user:
        await state.update_data(user_id=user["id"], user=user, password=None)
        await state.set_state(Form.awaiting_confirmation)

        await message.answer(
            "🔎 Проверьте данные:\n\n"
            f"*Сотрудник:* {user['name']}\n"
            f"*Логин:* {login}\n"
            f"*Компания:* {user.get('company_name', '—')}\n"
            f"*Должность:* {user.get('position', '—')}",
            reply_markup=get_identity_confirmation_keyboard(),
            parse_mode="Markdown",
        )
    else:
        await message.answer(
            "❌ Неверный логин или пароль. Попробуйте снова."
        )
        await state.update_data(password=None)
        await state.set_state(Form.entering_login)


# ✅ Подтверждение личности
@router.callback_query(F.data == "confirm_identity", Form.awaiting_confirmation)
async def identity_approved(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id")

    await callback.message.answer(
        "✅ Авторизация прошла успешно. Главное меню появилось снизу 👇",
        reply_markup=authorized_keyboard,
    )

    # Сразу показываем чек-листы (если нужно — раскомментируйте)
    # if user_id:
    #     checklists = get_checklists_for_user(user_id)
    #     if checklists:
    #         await callback.message.answer(
    #             "📋 Доступные чек-листы:",
    #             reply_markup=get_checklists_keyboard(checklists),
    #         )
    #     else:
    #         await callback.message.answer(
    #             "🙁 У вас пока нет доступных чек-листов.\n"
    #             "Если это ошибка — проверьте назначение чек-листов на вашу должность."
    #         )

    await state.set_state(Form.show_checklists)
    await callback.answer()


# ❌ Отклонение
@router.callback_query(F.data == "reject_identity", Form.awaiting_confirmation)
async def identity_rejected(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Попробуем снова. Введите ваш логин:")
    await state.set_state(Form.entering_login)
    await callback.answer()


# ✅ Обработка кнопки "Доступные чек-листы"
@router.message((F.text == "✅ Доступные чек-листы") | (F.text == "✅ доступные чек-листы"))
async def show_available_checklists(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id")

    if not user_id:
        await message.answer("⚠️ Сначала нужно авторизоваться через /start")
        return

    checklists = get_checklists_for_user(user_id)
    if checklists:
        await message.answer(
            "📋 Доступные чек-листы:",
            reply_markup=get_checklists_keyboard(checklists),
        )
        await state.set_state(Form.show_checklists)
    else:
        await message.answer("🙁 У вас пока нет доступных чек-листов.")


# ──────────────────────────────────────────────────────────────────────────────
# 📋 ПРОЙДЕННЫЕ ЧЕК-ЛИСТЫ — НОВЫЙ БЛОК (вместо старого show_completed_checklists)
# ──────────────────────────────────────────────────────────────────────────────

PAGE_LIMIT = 8  # показываем по 8 на страницу

def _build_completed_list_text(items, offset: int) -> str:
    if not items:
        return "Пока нет пройденных чек-листов."
    lines = ["Ваши последние чек-листы:\n"]
    for i, it in enumerate(items, start=1):
        idx = offset + i  # глобальная нумерация: 1..N
        dt = format_moscow(it["submitted_at"], "%d.%m.%Y %H:%M")
        lines.append(f"{idx}. {it['checklist_name']} — {dt}")
    return "\n".join(lines)

def _build_completed_list_kb(items, offset: int, total: int) -> InlineKeyboardMarkup:
    kb_rows = []

    # Кнопки с номерами текущих карточек (по 4 в ряд)
    number_buttons = []
    for i, it in enumerate(items, start=1):
        idx = offset + i
        number_buttons.append(
            InlineKeyboardButton(
                text=str(idx),
                callback_data=f"completed_view:{it['answer_id']}:{offset}"
            )
        )
        if len(number_buttons) == 4:
            kb_rows.append(number_buttons)
            number_buttons = []
    if number_buttons:
        kb_rows.append(number_buttons)

    # Навигация страниц (если всего больше лимита)
    if total > PAGE_LIMIT:
        nav_row = []
        if offset > 0:
            nav_row.append(
                InlineKeyboardButton(
                    text="⟵ Назад",
                    callback_data=f"completed_page:{max(0, offset - PAGE_LIMIT)}"
                )
            )
        if offset + PAGE_LIMIT < total:
            nav_row.append(
                InlineKeyboardButton(
                    text="Вперёд ⟶",
                    callback_data=f"completed_page:{offset + PAGE_LIMIT}"
                )
            )
        if nav_row:
            kb_rows.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=kb_rows)

@router.message((F.text == "📋 Пройденные чек-листы") | (F.text == "📋 пройденные чек-листы"))
async def handle_completed_list(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id")

    if not user_id:
        await message.answer("⚠️ Сначала нужно авторизоваться.")
        return

    offset = 0
    items, total = get_completed_answers_paginated(
        user_id=user_id,
        offset=offset,
        limit=PAGE_LIMIT
    )

    if total == 0:
        await message.answer("🕵️‍♂️ Вы ещё не проходили ни одного чек-листа.")
        return

    text = _build_completed_list_text(items, offset)
    kb = _build_completed_list_kb(items, offset, total)
    await message.answer(text, reply_markup=kb)

@router.callback_query(F.data.startswith("completed_page:"))
async def handle_completed_page(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id")

    if not user_id:
        await callback.answer("Не авторизованы", show_alert=True)
        return

    try:
        offset = int(callback.data.split(":")[1])
    except Exception:
        offset = 0

    items, total = get_completed_answers_paginated(
        user_id=user_id,
        offset=offset,
        limit=PAGE_LIMIT
    )
    text = _build_completed_list_text(items, offset)
    kb = _build_completed_list_kb(items, offset, total)

    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("completed_view:"))
async def handle_completed_view(callback: types.CallbackQuery):
    # формат: completed_view:<answer_id>:<offset>
    parts = callback.data.split(":")
    answer_id = int(parts[1])
    offset = int(parts[2]) if len(parts) > 2 else 0

    data = get_answer_report_data(answer_id)
    if not data:
        await callback.answer("Не удалось получить данные отчёта", show_alert=True)
        return

    res_line = f"\nРезультат: {data['result']}" if data.get("result") else ""
    text = (
        f"📋 <b>{data['checklist_name']}</b>\n"
        f"Дата: {data['date']}\n"
        f"Время: {data['time']}\n"
        f"Подразделение: {data['department']}{res_line}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📄 PDF",   callback_data=f"completed_pdf:{answer_id}:{offset}"),
            InlineKeyboardButton(text="📊 Excel", callback_data=f"completed_excel:{answer_id}:{offset}"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад к списку", callback_data=f"completed_page:{offset}")
        ]
    ])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("completed_pdf:"))
async def handle_completed_pdf(callback: types.CallbackQuery, state: FSMContext):
    # формат: completed_pdf:<answer_id>:<offset>
    parts = callback.data.split(":")
    answer_id = int(parts[1])
    offset = int(parts[2]) if len(parts) > 2 else 0

    await callback.answer()  # закрыть «часики»

    # 1) Собираем данные попытки из БД
    data = get_attempt_data(answer_id)
    state_data = await state.get_data()
    recent_departments = state_data.get("recent_departments") or {}
    override = recent_departments.get(str(answer_id)) if data else None
    if data:
        data = prepare_attempt_for_export(data, override)

    # 🔹 ЗАГРУЖАЕМ/ПРИВОДИМ ФОТО К ЛОКАЛЬНЫМ ПУТЯМ
    await _hydrate_photos_for_attempt(data, callback.bot)

    # 2) Генерим файлы (PDF + XLSX), но отправим только PDF
    pdf_path, xlsx_path = export_attempt_to_files(tmp_dir=None, data=data)

    try:
        # 3) Отправляем PDF
        await callback.message.answer_document(
            FSInputFile(pdf_path),
            caption=f"📄 Отчёт PDF — {data.checklist_name}\n{data.user_name} · {data.submitted_at:%d.%m.%Y %H:%M}",
        )
    finally:
        # 4) Чистим временные файлы
        for p in (pdf_path, xlsx_path):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass


@router.callback_query(F.data.startswith("completed_excel:"))
async def handle_completed_excel(callback: types.CallbackQuery, state: FSMContext):
    # формат: completed_excel:<answer_id>:<offset>
    parts = callback.data.split(":")
    answer_id = int(parts[1])
    offset = int(parts[2]) if len(parts) > 2 else 0

    await callback.answer()

    data = get_attempt_data(answer_id)
    state_data = await state.get_data()
    recent_departments = state_data.get("recent_departments") or {}
    override = recent_departments.get(str(answer_id)) if data else None
    if data:
        data = prepare_attempt_for_export(data, override)

    # 🔹 ЗАГРУЖАЕМ/ПРИВОДИМ ФОТО К ЛОКАЛЬНЫМ ПУТЯМ
    await _hydrate_photos_for_attempt(data, callback.bot)

    pdf_path, xlsx_path = export_attempt_to_files(tmp_dir=None, data=data)

    try:
        await callback.message.answer_document(
            FSInputFile(xlsx_path),
            caption=f"📊 Отчёт Excel — {data.checklist_name}\n{data.user_name} · {data.submitted_at:%d.%m.%Y %H:%M}",
        )
    finally:
        for p in (pdf_path, xlsx_path):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass



# ──────────────────────────────────────────────────────────────────────────────

@router.message((F.text == "ℹ️ Обо мне") | (F.text == "ℹ️ обо мне"))
async def show_user_info(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user = data.get("user")

    if not user:
        await message.answer("⚠️ Вы не авторизованы.")
        return

    text = (
        f"👤 *Информация о вас:*\n\n"
        f"*Фамилия и Имя:* {user['name']}\n"
        f"*Телефон:* {user['phone']}\n"
        f"*Компания:* {user.get('company_name', '—')}\n"
        f"*Должность:* {user.get('position', '—')}"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📋 Меню", callback_data="back_to_menu")]]
    )

    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard)


@router.callback_query(F.data == "back_to_menu")
async def return_to_main_menu(callback: types.CallbackQuery):
    await callback.message.answer("📋 Главное меню:", reply_markup=authorized_keyboard)
    await callback.answer()


@router.message((F.text == "🚪 Выйти") | (F.text == "🚪 выйти"))
async def handle_logout(message: types.Message, state: FSMContext):
    # исправленный относительный импорт!
    from ..keyboards.inline import get_start_keyboard

    await state.clear()
    await message.answer("🚪 Вы вышли из системы.")

    await message.answer(
        "👋 Добро пожаловать!\n\nНажмите *🚀 Начать*, чтобы пройти чек-лист.\n"
        "Или *📖 Инструкция*, чтобы узнать подробнее.",
        reply_markup=get_start_keyboard(),
        parse_mode="Markdown",
    )

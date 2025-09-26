# handlers/fsm_completed.py — пройденные чек-листы, отчёты
import os

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile,
)

from ..services.completed import CompletedService         # сервис вместо прямых вызовов bot_logic
from ..export import export_attempt_to_files
from ..utils.media import hydrate_photos_for_attempt      # вынесенный хелпер

router = Router()

# ──────────────────────────────────────────────────────────────────────────────
# 📋 ПРОЙДЕННЫЕ ЧЕК-ЛИСТЫ
# ──────────────────────────────────────────────────────────────────────────────

PAGE_LIMIT = 8  # показываем по 8 на страницу


def _build_completed_list_text(items, offset: int) -> str:
    if not items:
        return "Пока нет пройденных чек-листов."
    lines = ["Ваши последние чек-листы:\n"]
    for i, it in enumerate(items, start=1):
        idx = offset + i  # глобальная нумерация: 1..N
        dt = it["submitted_at"].strftime("%d.%m.%Y %H:%M")
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
                callback_data=f"completed_view:{it['answer_id']}:{offset}",
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
                    callback_data=f"completed_page:{max(0, offset - PAGE_LIMIT)}",
                )
            )
        if offset + PAGE_LIMIT < total:
            nav_row.append(
                InlineKeyboardButton(
                    text="Вперёд ⟶",
                    callback_data=f"completed_page:{offset + PAGE_LIMIT}",
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
    svc = CompletedService()
    items, total = svc.get_paginated(user_id=user_id, offset=offset, limit=PAGE_LIMIT)

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

    svc = CompletedService()
    items, total = svc.get_paginated(user_id=user_id, offset=offset, limit=PAGE_LIMIT)

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

    svc = CompletedService()
    preview = svc.get_report_preview(answer_id)
    if not preview:
        await callback.answer("Не удалось получить данные отчёта", show_alert=True)
        return

    res_line = f"\nРезультат: {preview['result']}" if preview.get("result") else ""
    text = (
        f"📋 <b>{preview['checklist_name']}</b>\n"
        f"Дата: {preview['date']}\n"
        f"Время: {preview['time']}\n"
        f"Подразделение: {preview['department']}{res_line}"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📄 PDF", callback_data=f"completed_pdf:{answer_id}:{offset}"),
                InlineKeyboardButton(text="📊 Excel", callback_data=f"completed_excel:{answer_id}:{offset}"),
            ],
            [InlineKeyboardButton(text="⬅️ Назад к списку", callback_data=f"completed_page:{offset}")],
        ]
    )

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("completed_pdf:"))
async def handle_completed_pdf(callback: types.CallbackQuery):
    # формат: completed_pdf:<answer_id>:<offset>
    parts = callback.data.split(":")
    answer_id = int(parts[1])
    # offset = int(parts[2]) if len(parts) > 2 else 0  # если нужно — можно использовать

    await callback.answer()  # закрыть «часики»

    # 1) Собираем данные попытки из БД
    svc = CompletedService()
    data = svc.get_attempt(answer_id)

    # 🔹 ЗАГРУЖАЕМ/ПРИВОДИМ ФОТО К ЛОКАЛЬНЫМ ПУТЯМ
    await hydrate_photos_for_attempt(data, callback.bot)

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
async def handle_completed_excel(callback: types.CallbackQuery):
    # формат: completed_excel:<answer_id>:<offset>
    parts = callback.data.split(":")
    answer_id = int(parts[1])
    # offset = int(parts[2]) if len(parts) > 2 else 0

    await callback.answer()

    svc = CompletedService()
    data = svc.get_attempt(answer_id)

    # 🔹 ЗАГРУЖАЕМ/ПРИВОДИМ ФОТО К ЛОКАЛЬНЫМ ПУТЯМ
    await hydrate_photos_for_attempt(data, callback.bot)

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

# handlers/fsm.py

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from states import Form
from bot_logic import find_user_by_name_phone_company, get_checklists_for_user
from keyboards.inline import get_identity_confirmation_keyboard, get_checklists_keyboard

router = Router()

@router.callback_query(F.data == "start_checklist")
async def ask_name(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите вашу *Фамилию и Имя*:")
    await state.set_state(Form.entering_name)
    await callback.answer()

@router.message(Form.entering_name)
async def ask_phone(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer("Введите ваш номер телефона:")
    await state.set_state(Form.entering_phone)

@router.message(Form.entering_phone)
async def confirm_user(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text.strip())
    data = await state.get_data()

    user = find_user_by_name_phone_company(data["name"], data["phone"], company_name=None)
    if user:
        await state.update_data(user_id=user["id"])
        await state.set_state(Form.show_checklists)

        await message.answer(
            f"🔎 Проверьте данные:\n\n"
            f"*Фамилия и Имя:* {user['name']}\n"
            f"*Телефон:* {user['phone']}\n"
            f"*Компания:* {user.get('company_name', '—')}\n"
            f"*Должность:* {user['position']}",
            reply_markup=get_identity_confirmation_keyboard(),
            parse_mode="Markdown"
        )
    else:
        await message.answer("Пользователь не найден. Проверьте данные и попробуйте снова.")
        await state.set_state(Form.entering_name)

@router.callback_query(F.data == "confirm_identity", Form.show_checklists)
async def identity_approved(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    checklists = get_checklists_for_user(data["user_id"])
    if not checklists:
        await callback.message.answer("Нет доступных чек-листов.")
        await state.clear()
    else:
        await callback.message.answer(
            "Выберите чек-лист для прохождения:",
            reply_markup=get_checklists_keyboard(checklists)
        )
        await state.set_state(Form.show_checklists)
    await callback.answer()

@router.callback_query(F.data == "reject_identity", Form.show_checklists)
async def identity_rejected(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Попробуем снова. Введите вашу *Фамилию и Имя*:")
    await state.set_state(Form.entering_name)
    await callback.answer()

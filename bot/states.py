from aiogram.fsm.state import State, StatesGroup

class Form(StatesGroup):
    entering_login = State()
    entering_password = State()
    awaiting_confirmation = State()
    selecting_department = State()
    entering_custom_department = State()
    confirming_resume = State()
    choosing_checklist_mode = State()
    show_checklists = State()
    answering_question = State()
    answering_block = State()
    adding_comment = State()
    adding_photo = State()
    manual_text_answer = State()
    text_decision = State()

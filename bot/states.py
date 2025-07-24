from aiogram.fsm.state import State, StatesGroup

class Form(StatesGroup):
    entering_phone = State()
    show_checklists = State()
    answering_question = State()
    adding_comment = State()
    adding_photo = State()
    entering_name = State()
    manual_text_answer = State()

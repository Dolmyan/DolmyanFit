from aiogram.fsm.state import State, StatesGroup


class CalcState(StatesGroup):
    waiting_for_data = State()
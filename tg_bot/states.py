from aiogram.fsm.state import StatesGroup, State

class RegistrationStates(StatesGroup):
    waiting_for_role = State()           # Выбор: Студент или Преподаватель
    # Ветка студента
    waiting_for_group = State()          # Выбор учебной группы
    waiting_for_format = State()         # Выбор формата (Текст / Изображение)
    waiting_for_notifications = State()  # Включение/выключение уведомлений
    # Ветка преподавателя
    waiting_for_teacher_name = State()   # Ввод ФИО для сверки со списком базы

class TeacherActionStates(StatesGroup):
    waiting_for_comment = State() # Ожидание ввода текста комментария

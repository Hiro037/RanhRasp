from datetime import date
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from utils.timezone import get_now


def get_inline_main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Генерирует инлайн главная меню (3 кнопки для студента, 4 для админа)."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Посмотреть расписание", callback_data="menu:schedule")
    builder.button(text="⚙️ Настройки профиля", callback_data="menu:settings")
    builder.button(text="✍️ Написать админам", callback_data="menu:feedback")

    if is_admin:
        builder.button(text="📊 Статистика базы", callback_data="menu:admin_stats")

    builder.adjust(1)  # Кнопки одна под другой для красоты
    return builder.as_markup()


def get_schedule_keyboard(target_date: date, has_next: bool, role: str = "student") -> InlineKeyboardMarkup:
    """
    Формирует клавиатуру пагинации дней.
    Если target_date == сегодня, кнопка 'Предыдущий день' не показывается.
    Если has_next == False, кнопка 'Следующий день' не показывается.
    Для преподавателя добавляется кнопка '✏️ Добавить комментарий'.
    """
    today = get_now().date()
    date_str = target_date.strftime("%Y-%m-%d")
    builder = InlineKeyboardBuilder()

    # Кнопка "Предыдущий день" – только если это не сегодня
    if target_date != today:
        builder.button(text="⬅️ Предыдущий день", callback_data=f"sched_nav:prev:{date_str}")

    # Кнопка обновления всегда
    builder.button(text="🔄 Обновить", callback_data=f"sched_nav:refresh:{date_str}")

    # Кнопка "Следующий день" – только если есть будущие занятия
    if has_next:
        builder.button(text="Следующий день ➡️", callback_data=f"sched_nav:next:{date_str}")

    # Кнопка добавления комментария – только для преподавателя
    if role == "teacher":
        builder.button(text="✏️ Добавить комментарий", callback_data=f"add_comment_for_date:{date_str}")

    builder.button(text="🔙 Главное меню", callback_data="menu:back")
    builder.adjust(1)  # все кнопки в столбец
    return builder.as_markup()

def get_schedule_period_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора периода расписания: сегодня, завтра, эта неделя, след. неделя."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Сегодня", callback_data="schedule:today")
    builder.button(text="📆 Завтра", callback_data="schedule:tomorrow")
    builder.button(text="📅 Эта неделя", callback_data="schedule:this_week")
    builder.button(text="📆 Следующая неделя", callback_data="schedule:next_week")
    builder.button(text="🔙 Главное меню", callback_data="menu:back")
    builder.adjust(2, 2, 1)  # две строки по две кнопки, затем одна кнопка
    return builder.as_markup()

def get_admin_menu_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура админ-панели: статистика и запросы."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика", callback_data="admin:stats")
    builder.button(text="📥 Запросы (фидбек/заявки)", callback_data="admin:requests")
    builder.button(text="🔙 Главное меню", callback_data="menu:back")
    builder.adjust(1)
    return builder.as_markup()

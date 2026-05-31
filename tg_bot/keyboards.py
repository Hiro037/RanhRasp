from datetime import date
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


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


def get_schedule_keyboard(target_date: date, has_next: bool) -> InlineKeyboardMarkup:
    """
    Формирует клавиатуру пагинации дней.
    Если has_next=False, кнопка 'Вперед' скрывается/заменяется.
    """
    date_str = target_date.strftime("%Y-%m-%d")
    builder = InlineKeyboardBuilder()

    # Кнопки: Назад | Обновить
    builder.button(text="⬅️ Предыдущий день", callback_data=f"sched_nav:prev:{date_str}")
    builder.button(text="🔄 Обновить", callback_data=f"sched_nav:refresh:{date_str}")

    # Динамическая проверка кнопки "Вперед"
    if has_next:
        builder.button(text="Следующий день ➡️", callback_data=f"sched_nav:next:{date_str}")
    else:
        # Если пар впереди нет — показываем заглушку, чтобы не ломать верстку
        builder.button(text="⏸️ Пары закончились", callback_data="void")

    builder.button(text="🔙 Главное меню", callback_data="menu:back")
    builder.adjust(2, 1 if has_next else 1, 1)
    return builder.as_markup()

from datetime import date
from vkbottle import Keyboard, KeyboardButtonColor, Text

from utils.timezone import get_now


def get_vk_inline_main_menu(is_admin: bool = False) -> str:
    kb = Keyboard(inline=True)
    kb.add(Text("📅 Расписание", payload={"menu": "schedule"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Text("⚙️ Настройки", payload={"menu": "settings"}), color=KeyboardButtonColor.SECONDARY)
    kb.add(Text("✍️ Отзыв", payload={"menu": "feedback"}), color=KeyboardButtonColor.SECONDARY)

    if is_admin:
        kb.row()
        kb.add(Text("📊 Статистика", payload={"menu": "admin_stats"}), color=KeyboardButtonColor.NEGATIVE)
    return kb.get_json()


def get_vk_schedule_keyboard(target_date: date, has_next: bool, role: str = "student") -> str:
    """
    VK-версия клавиатуры пагинации.
    - Если target_date == сегодня, кнопка '⬅️ День' НЕ показывается.
    - Если has_next == False, кнопка 'День ➡️' НЕ показывается.
    - Для преподавателя добавляется кнопка '✏️ Комментарий'.
    """
    today = get_now().date()
    date_str = target_date.strftime("%Y-%m-%d")
    kb = Keyboard(inline=True)

    # Кнопка "Предыдущий день" – только если это не сегодня
    if target_date != today:
        kb.add(Text("⬅️ День", payload={"vk_nav": f"prev:{date_str}"}), color=KeyboardButtonColor.PRIMARY)

    # Кнопка обновления всегда
    kb.add(Text("🔄", payload={"vk_nav": f"refresh:{date_str}"}), color=KeyboardButtonColor.SECONDARY)

    # Кнопка "Следующий день" – только если есть будущие занятия
    if has_next:
        kb.add(Text("День ➡️", payload={"vk_nav": f"next:{date_str}"}), color=KeyboardButtonColor.PRIMARY)

    # Кнопка комментария для преподавателя
    if role == "teacher":
        kb.row()
        kb.add(Text("✏️ Комментарий", payload={"add_comment_for_date": date_str}), color=KeyboardButtonColor.NEGATIVE)

    kb.row()
    kb.add(Text("🔙 Главное меню", payload={"menu": "back"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def get_vk_schedule_period_keyboard() -> str:
    kb = Keyboard(inline=True)
    kb.add(Text("📅 Сегодня", payload={"menu": "schedule_today"}), color=KeyboardButtonColor.PRIMARY)
    kb.add(Text("📆 Завтра", payload={"menu": "schedule_tomorrow"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Text("📅 Эта неделя", payload={"menu": "schedule_this_week"}), color=KeyboardButtonColor.SECONDARY)
    kb.add(Text("📆 Следующая неделя", payload={"menu": "schedule_next_week"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Text("🔙 Главное меню", payload={"menu": "back"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def get_vk_schedule_keyboard(target_date: date, has_next: bool, role: str = "student") -> str:
    today = get_now().date()
    date_str = target_date.strftime("%Y-%m-%d")
    kb = Keyboard(inline=True)

    if target_date != today:
        kb.add(Text("⬅️ День", payload={"vk_nav": f"prev:{date_str}"}), color=KeyboardButtonColor.PRIMARY)
    kb.add(Text("🔄", payload={"vk_nav": f"refresh:{date_str}"}), color=KeyboardButtonColor.SECONDARY)
    if has_next:
        kb.add(Text("День ➡️", payload={"vk_nav": f"next:{date_str}"}), color=KeyboardButtonColor.PRIMARY)

    if role == "teacher":
        kb.row()
        kb.add(Text("✏️ Комментарий", payload={"add_comment_for_date": date_str}), color=KeyboardButtonColor.NEGATIVE)

    kb.row()
    kb.add(Text("🔙 Главное меню", payload={"menu": "back"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()

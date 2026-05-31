from datetime import date
from vkbottle import Keyboard, KeyboardButtonColor, Text


def get_vk_inline_main_menu(is_admin: bool = False) -> str:
    kb = Keyboard(one_time=False, inline=True)
    kb.add(Text("📅 Расписание", payload={"menu": "schedule"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Text("⚙️ Настройки", payload={"menu": "settings"}), color=KeyboardButtonColor.SECONDARY)
    kb.add(Text("✍️ Отзыв", payload={"menu": "feedback"}), color=KeyboardButtonColor.SECONDARY)

    if is_admin:
        kb.row()
        kb.add(Text("📊 Статистика", payload={"menu": "admin_stats"}), color=KeyboardButtonColor.NEGATIVE)
    return kb.get_json()


def get_vk_schedule_keyboard(target_date: date, has_next: bool) -> str:
    date_str = target_date.strftime("%Y-%m-%d")
    kb = Keyboard(one_time=False, inline=True)

    # Кнопка назад и обновить
    kb.add(Text("⬅️ День", payload={"vk_nav": f"prev:{date_str}"}), color=KeyboardButtonColor.PRIMARY)
    kb.add(Text("🔄", payload={"vk_nav": f"refresh:{date_str}"}), color=KeyboardButtonColor.SECONDARY)

    if has_next:
        kb.add(Text("День ➡️", payload={"vk_nav": f"next:{date_str}"}), color=KeyboardButtonColor.PRIMARY)

    kb.row()
    kb.add(Text("🔙 Главное меню", payload={"menu": "back"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()
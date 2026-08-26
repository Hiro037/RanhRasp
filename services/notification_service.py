"""
Сервис для отправки уведомлений администраторам (кроссплатформенный).
"""

from html import escape as html_escape

from config import settings
from tg_bot.loader import tg_bot
from vk_bot.loader import vk_bot


async def notify_admins_about_teacher_request(platform: str, user_id: int, teacher_name: str, request_id: int):
    """
    Отправляет уведомление всем админам на указанной платформе о новой заявке.
    Для Telegram использует инлайн-кнопки, для VK – текстовые команды (упрощённо).
    """
    if platform == "telegram":
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Принять", callback_data=f"quick_approve_req:{request_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"quick_reject_req:{request_id}")
            ]
        ])
        text = (
            f"📝 <b>Новая заявка на верификацию преподавателя!</b>\n\n"
            f"👤 ID пользователя: <code>{user_id}</code>\n"
            f"✍️ Введённое ФИО: <b>{html_escape(teacher_name)}</b>\n\n"
            f"Используйте кнопки ниже для быстрой обработки, "
            f"или зайдите в админ-панель для выбора конкретного преподавателя из списка."
        )
        for admin_id in settings.TG_ADMINS:
            try:
                await tg_bot.send_message(chat_id=admin_id, text=text, parse_mode="HTML", reply_markup=keyboard)
            except Exception as e:
                print(f"Не удалось отправить уведомление админу {admin_id}: {e}")

    elif platform == "vk":
        # Для VK – упрощённо: отправляем сообщение с инструкцией (кнопки сложнее в реализации без callback)
        text = (
            f"📝 Новая заявка на верификацию преподавателя!\n\n"
            f"👤 ID пользователя: {user_id}\n"
            f"✍️ ФИО: {teacher_name}\n\n"
            f"Для обработки используйте команды в админ-панели:\n"
            f"👉 Одобрить заявку {request_id}\n"
            f"👉 Отклонить заявку {request_id}"
        )
        for admin_id in settings.VK_ADMINS:
            try:
                await vk_bot.api.messages.send(peer_id=admin_id, message=text, random_id=0)
            except Exception as e:
                print(f"Не удалось отправить уведомление админу VK {admin_id}: {e}")

import json
from vkbottle.bot import BotLabeler, Message
from vkbottle import Keyboard, KeyboardButtonColor, Text
from vkbottle import BaseStateGroup
from sqlalchemy import select

from database.connection import async_session_maker
from database.models import User
from services import user_service
from config import settings
from vk_bot.loader import vk_bot

vk_settings_labeler = BotLabeler()


class VkFeedbackStates(BaseStateGroup):
    WAITING_FOR_FEEDBACK = "waiting_for_feedback"


async def get_vk_settings_kb(user: User) -> Keyboard:
    msg_type = "📝 Текст" if user.schedule_message_type == "text" else "🖼️ Картинка"
    notif_status = "🔔 Вкл" if user.notifications_enabled else "🔕 Выкл"

    kb = (
        Keyboard(inline=True)
        .add(Text(f"📊 Формат: {msg_type}", payload={"set_tg": "type"}), color=KeyboardButtonColor.PRIMARY)
        .row()
        .add(Text(f"📢 Уведомления: {notif_status}", payload={"set_tg": "notif"}), color=KeyboardButtonColor.PRIMARY)
        .row()
        .add(Text("✍️ Написать админам", payload={"set_tg": "feedback"}), color=KeyboardButtonColor.POSITIVE)
        .row()
        .add(Text("🔙 Главное меню", payload={"menu": "back"}), color=KeyboardButtonColor.SECONDARY)
    )
    return kb


@vk_settings_labeler.message(
    func=lambda msg: msg.payload is not None and json.loads(msg.payload).get("menu") == "settings")
async def vk_show_settings(message: Message):
    async with async_session_maker() as session:
        user = await user_service.get_user_by_platform_id(session, "vk", message.from_id)

    if not user: return
    kb = await get_vk_settings_kb(user)
    await message.answer("⚙️ Управление вашим профилем и уведомлениями (ВК):", keyboard=kb.get_json())


@vk_settings_labeler.message(func=lambda msg: msg.payload is not None and "set_tg" in json.loads(msg.payload))
async def vk_toggle_settings(message: Message):
    action = json.loads(message.payload)["set_tg"]

    if action == "feedback":
        await vk_bot.state_dispenser.set(message.from_id, VkFeedbackStates.WAITING_FOR_FEEDBACK)
        kb = Keyboard(inline=True).add(Text("❌ Отмена", payload={"menu": "settings"}),
                                       color=KeyboardButtonColor.NEGATIVE)
        await message.answer("📥 Напишите ваше предложение или жалобу одним сообщением:", keyboard=kb.get_json())
        return

    async with async_session_maker() as session:
        stmt = select(User).where(User.platform == "vk", User.platform_user_id == str(message.from_id))
        res = await session.execute(stmt)
        user = res.scalars().first()

        if user:
            if action == "type":
                user.schedule_message_type = "image" if user.schedule_message_type == "text" else "text"
            elif action == "notif":
                user.notifications_enabled = not user.notifications_enabled
            await session.commit()

            kb = await get_vk_settings_kb(user)
            await message.answer("✅ Настройки обновлены!", keyboard=kb.get_json())


@vk_settings_labeler.message(state=VkFeedbackStates.WAITING_FOR_FEEDBACK)
async def vk_process_feedback(message: Message):
    feedback_text = message.text.strip()
    await vk_bot.state_dispenser.delete(message.from_id)

    from main_loader import tg_bot

    # Отправляем уведомление админам в Telegram (так как консоль администрирования обычно там централизована)
    admin_alert = (
        f"📩 *Получен новый отзыв/жалоба!*\n\n"
        f"👤 Отправитель: VK User (ID: {message.from_id})\n"
        f"📱 Платформа: ВКонтакте\n"
        f"💬 Текст: {feedback_text}"
    )

    for admin_id in settings.ADMIN_IDS:
        try:
            await tg_bot.send_message(chat_id=admin_id, text=admin_alert, parse_mode="Markdown")
        except Exception:
            pass

    await message.answer("✅ Ваше обращение успешно передано администрации проекта!")

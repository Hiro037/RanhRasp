from vkbottle.bot import Blueprint, Message
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import User
from services.user_service import get_or_create_user, update_user_preferences, create_feedback, update_user_group

bp = Blueprint("SettingsFeedbackHandlers")


@bp.on.message(text="Настройки")
async def settings_main_vk(message: Message):
    session: AsyncSession = message.ctx_api.session
    user = await get_or_create_user(session, "vk", message.from_id)

    notify_text = "Включены" if user.is_notification_on else "Выключены"
    format_text = "Картинка" if user.schedule_message_type == "pic" else "Текст"
    group_text = user.groups[0].name if user.groups else "Не выбрана"

    return (
        f"⚙ Настройки вашего профиля:\n"
        f"1. Уведомления: {notify_text} (Напишите 'Переключить уведомления')\n"
        f"2. Формат: {format_text} (Напишите 'Переключить формат')\n"
        f"3. Ваша группа: {group_text} (Напишите 'Поменять группу [Имя группы]')"
    )


@bp.on.message(text="Переключить уведомления")
async def toggle_not_vk(message: Message):
    session: AsyncSession = message.ctx_api.session
    user = await get_or_create_user(session, "vk", message.from_id)
    await update_user_preferences(session, user.id, is_notification_on=not user.is_notification_on)
    return "✅ Настройки уведомлений успешно изменены!"


@bp.on.message(text="Переключить формат")
async def toggle_fmt_vk(message: Message):
    session: AsyncSession = message.ctx_api.session
    user = await get_or_create_user(session, "vk", message.from_id)
    new_fmt = "text" if user.schedule_message_type == "pic" else "pic"
    await update_user_preferences(session, user.id, schedule_type=new_fmt)
    return f"✅ Формат расписания изменен на: {new_fmt}"


@bp.on.message(text="Поменять группу <group_name>")
async def change_grp_vk(message: Message, group_name: str):
    session: AsyncSession = message.ctx_api.session
    user = await get_or_create_user(session, "vk", message.from_id)
    success = await update_user_group(session, user.id, group_name.strip())
    if success:
        return f"✅ Ваша группа успешно изменена на {group_name}!"
    return "❌ Ошибка. Такой группы не найдено в базе данных."

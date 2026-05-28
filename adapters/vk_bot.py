"""
VK bot adapter using vkbottle framework with Redis FSM.
Full registration flow identical to Telegram bot.
"""

import json
from typing import Optional

from vkbottle import Bot, Keyboard, KeyboardButtonColor, Text
from vkbottle.bot import BotLabeler, Message
from vkbottle.dispatch.rules.base import CommandRule, PayloadRule
from redis import asyncio as aioredis

from core.config import settings
from core.database import AsyncSessionLocal
from core.services import (
    get_or_create_user, get_all_groups, set_user_role_student,
    set_user_role_teacher_request, update_notification_setting,
    update_message_type, get_user_by_id
)
from core.models import Platform, ScheduleMessageType

# Redis client
redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)

bp = BotLabeler()
bot = Bot(token=settings.vk_group_token)

# ---------- Helper functions for FSM ----------
async def get_state(user_id: int) -> Optional[str]:
    """Get current state from Redis."""
    return await redis_client.get(f"vk_state:{user_id}")

async def set_state(user_id: int, state: str) -> None:
    """Set state in Redis."""
    await redis_client.set(f"vk_state:{user_id}", state)

async def delete_state(user_id: int) -> None:
    """Delete state from Redis."""
    await redis_client.delete(f"vk_state:{user_id}")

async def get_state_data(user_id: int) -> dict:
    """Get additional state data from Redis."""
    data = await redis_client.get(f"vk_state_data:{user_id}")
    return json.loads(data) if data else {}

async def set_state_data(user_id: int, data: dict) -> None:
    """Set additional state data in Redis."""
    await redis_client.set(f"vk_state_data:{user_id}", json.dumps(data))

async def delete_state_data(user_id: int) -> None:
    """Delete additional state data from Redis."""
    await redis_client.delete(f"vk_state_data:{user_id}")

# ---------- Helper functions ----------
async def get_user_from_event(event: Message) -> dict:
    """Extract or create user from DB."""
    user_id = event.from_id
    name = f"user_{user_id}"
    try:
        user_info = await bot.api.users.get(user_ids=user_id, fields=["first_name", "last_name"])
        if user_info:
            name = f"{user_info[0].first_name} {user_info[0].last_name}"
    except:
        pass
    async with AsyncSessionLocal() as db:
        user = await get_or_create_user(db, Platform.VK, user_id, name)
    return {"id": user.id, "tg_id": user.tg_id, "vk_id": user.vk_id, "name": user.name}

# ---------- FSM states ----------
class RegStates:
    ROLE = "role"
    GROUP = "group"
    FORMAT = "format"
    NOTIFICATION = "notification"

# ---------- Keyboards ----------
def role_keyboard():
    keyboard = Keyboard(inline=True)
    keyboard.add(Text("👨‍🎓 Студент", payload={"cmd": "role_student"}), color=KeyboardButtonColor.PRIMARY)
    keyboard.row()
    keyboard.add(Text("👨‍🏫 Преподаватель", payload={"cmd": "role_teacher"}), color=KeyboardButtonColor.SECONDARY)
    return keyboard

def group_keyboard(groups):
    keyboard = Keyboard(inline=True)
    for group in groups:
        keyboard.add(Text(group.name, payload={"cmd": "group", "group_id": group.id}), color=KeyboardButtonColor.PRIMARY)
        keyboard.row()
    keyboard.add(Text("🔙 Назад", payload={"cmd": "back_role"}), color=KeyboardButtonColor.SECONDARY)
    return keyboard

def format_keyboard():
    keyboard = Keyboard(inline=True)
    keyboard.add(Text("🖼 Картинкой", payload={"cmd": "format_pic"}), color=KeyboardButtonColor.PRIMARY)
    keyboard.row()
    keyboard.add(Text("📝 Текстом", payload={"cmd": "format_text"}), color=KeyboardButtonColor.PRIMARY)
    keyboard.row()
    keyboard.add(Text("🔙 Назад", payload={"cmd": "back_group"}), color=KeyboardButtonColor.SECONDARY)
    return keyboard

def notification_keyboard():
    keyboard = Keyboard(inline=True)
    keyboard.add(Text("✅ Да", payload={"cmd": "notif_on"}), color=KeyboardButtonColor.POSITIVE)
    keyboard.row()
    keyboard.add(Text("❌ Нет", payload={"cmd": "notif_off"}), color=KeyboardButtonColor.NEGATIVE)
    keyboard.row()
    keyboard.add(Text("🔙 Назад", payload={"cmd": "back_format"}), color=KeyboardButtonColor.SECONDARY)
    return keyboard

# ---------- Command /start ----------
@bp.message(CommandRule("/start"))
async def start_handler(event: Message):
    user_data = await get_user_from_event(event)
    user_id = event.from_id

    async with AsyncSessionLocal() as db:
        user = await get_user_by_id(db, user_data["id"])
        if user and (user.teacher_profile_id is not None or user.groups):
            await event.answer("✅ Вы уже зарегистрированы. Основное меню будет доступно в следующей версии.\nПока вы можете использовать команды: /start - сбросить регистрацию, /help.")
            return

    await set_state(user_id, RegStates.ROLE)
    await event.answer("🎓 Добро пожаловать в бот расписания!\n\nКто вы?", keyboard=role_keyboard())

# ---------- Role selection ----------
@bp.message(PayloadRule({"cmd": "role_student"}))
async def role_student_handler(event: Message):
    user_id = event.from_id
    state = await get_state(user_id)
    if state != RegStates.ROLE:
        return

    async with AsyncSessionLocal() as db:
        groups = await get_all_groups(db)
    if not groups:
        await event.answer("❌ Группы не найдены. Обратитесь к администратору.")
        await delete_state(user_id)
        return

    await set_state(user_id, RegStates.GROUP)
    await event.answer("Выберите вашу группу:", keyboard=group_keyboard(groups))

@bp.message(PayloadRule({"cmd": "role_teacher"}))
async def role_teacher_handler(event: Message):
    user_id = event.from_id
    state = await get_state(user_id)
    if state != RegStates.ROLE:
        return

    user_data = await get_user_from_event(event)
    async with AsyncSessionLocal() as db:
        await set_user_role_teacher_request(db, user_data["id"])

    await delete_state(user_id)
    await event.answer(
        "👨‍🏫 Вы выбрали роль преподавателя.\n\n"
        "Для доступа к функциям преподавателя необходимо подтверждение администратора. "
        "Администратор будет уведомлён. Пожалуйста, ожидайте.\n\n"
        "Вы можете продолжать пользоваться ботом как студент, но для этого зарегистрируйтесь заново с командой /start и выберите 'Студент'."
    )

# ---------- Group selection ----------
@bp.message(PayloadRule({"cmd": "group"}))
async def group_handler(event: Message):
    user_id = event.from_id
    state = await get_state(user_id)
    if state != RegStates.GROUP:
        return

    payload = json.loads(event.payload) if event.payload else {}
    group_id = payload.get("group_id")
    if group_id is None:
        return

    data = await get_state_data(user_id)
    data["group_id"] = group_id
    await set_state_data(user_id, data)
    await set_state(user_id, RegStates.FORMAT)

    await event.answer("В каком формате вы хотите получать расписание?", keyboard=format_keyboard())

@bp.message(PayloadRule({"cmd": "back_role"}))
async def back_to_role(event: Message):
    user_id = event.from_id
    await set_state(user_id, RegStates.ROLE)
    await delete_state_data(user_id)
    await event.answer("Кто вы?", keyboard=role_keyboard())

# ---------- Format selection ----------
@bp.message(PayloadRule({"cmd": "format_pic"}))
async def format_pic_handler(event: Message):
    user_id = event.from_id
    state = await get_state(user_id)
    if state != RegStates.FORMAT:
        return

    data = await get_state_data(user_id)
    data["message_type"] = ScheduleMessageType.PICTURE.value
    await set_state_data(user_id, data)
    await set_state(user_id, RegStates.NOTIFICATION)

    await event.answer("Хотите получать ежедневные уведомления о расписании на завтра?", keyboard=notification_keyboard())

@bp.message(PayloadRule({"cmd": "format_text"}))
async def format_text_handler(event: Message):
    user_id = event.from_id
    state = await get_state(user_id)
    if state != RegStates.FORMAT:
        return

    data = await get_state_data(user_id)
    data["message_type"] = ScheduleMessageType.TEXT.value
    await set_state_data(user_id, data)
    await set_state(user_id, RegStates.NOTIFICATION)

    await event.answer("Хотите получать ежедневные уведомления о расписании на завтра?", keyboard=notification_keyboard())

@bp.message(PayloadRule({"cmd": "back_group"}))
async def back_to_group(event: Message):
    user_id = event.from_id
    async with AsyncSessionLocal() as db:
        groups = await get_all_groups(db)
    if not groups:
        await event.answer("❌ Группы не найдены. Обратитесь к администратору.")
        await delete_state(user_id)
        await delete_state_data(user_id)
        return
    await set_state(user_id, RegStates.GROUP)
    await event.answer("Выберите вашу группу:", keyboard=group_keyboard(groups))

# ---------- Notification selection ----------
@bp.message(PayloadRule({"cmd": "notif_on"}))
async def notif_on_handler(event: Message):
    user_id = event.from_id
    state = await get_state(user_id)
    if state != RegStates.NOTIFICATION:
        return

    data = await get_state_data(user_id)
    group_id = data.get("group_id")
    msg_type_str = data.get("message_type", ScheduleMessageType.TEXT.value)
    msg_type = ScheduleMessageType(msg_type_str)

    user_data = await get_user_from_event(event)
    async with AsyncSessionLocal() as db:
        user = await get_user_by_id(db, user_data["id"])
        if user:
            await set_user_role_student(db, user.id, group_id)
            await update_notification_setting(db, user.id, True)
            await update_message_type(db, user.id, msg_type)

    await delete_state(user_id)
    await delete_state_data(user_id)
    await event.answer(
        "✅ Регистрация завершена!\n\n"
        "Теперь вы можете использовать:\n"
        "/schedule - расписание на сегодня\n"
        "/tomorrow - расписание на завтра\n"
        "/week - расписание на неделю\n"
        "/settings - настройки\n"
        "/help - помощь"
    )

@bp.message(PayloadRule({"cmd": "notif_off"}))
async def notif_off_handler(event: Message):
    user_id = event.from_id
    state = await get_state(user_id)
    if state != RegStates.NOTIFICATION:
        return

    data = await get_state_data(user_id)
    group_id = data.get("group_id")
    msg_type_str = data.get("message_type", ScheduleMessageType.TEXT.value)
    msg_type = ScheduleMessageType(msg_type_str)

    user_data = await get_user_from_event(event)
    async with AsyncSessionLocal() as db:
        user = await get_user_by_id(db, user_data["id"])
        if user:
            await set_user_role_student(db, user.id, group_id)
            await update_notification_setting(db, user.id, False)
            await update_message_type(db, user.id, msg_type)

    await delete_state(user_id)
    await delete_state_data(user_id)
    await event.answer(
        "✅ Регистрация завершена!\n\n"
        "Теперь вы можете использовать:\n"
        "/schedule - расписание на сегодня\n"
        "/tomorrow - расписание на завтра\n"
        "/week - расписание на неделю\n"
        "/settings - настройки\n"
        "/help - помощь"
    )

@bp.message(PayloadRule({"cmd": "back_format"}))
async def back_to_format(event: Message):
    user_id = event.from_id
    await set_state(user_id, RegStates.FORMAT)
    await event.answer("В каком формате вы хотите получать расписание?", keyboard=format_keyboard())

# ---------- Help command ----------
@bp.message(CommandRule("/help"))
async def help_handler(event: Message):
    text = (
        "📚 Помощь\n\n"
        "/start - начать регистрацию\n"
        "/schedule - расписание на сегодня\n"
        "/tomorrow - расписание на завтра\n"
        "/week - расписание на неделю\n"
        "/settings - изменить настройки\n"
        "/help - это сообщение"
    )
    await event.answer(text)

# ---------- Admin command ----------
@bp.message(CommandRule("/admin"))
async def admin_handler(event: Message):
    admin_ids = settings.admin_vk_ids
    if event.from_id not in admin_ids:
        await event.answer("⛔ У вас нет прав администратора.")
        return
    async with AsyncSessionLocal() as db:
        from core.services import get_users_without_teacher_and_group
        users = await get_users_without_teacher_and_group(db)
        if not users:
            await event.answer("Нет заявок от преподавателей.")
            return
        text = "📋 Заявки на роль преподавателя:\n\n"
        for u in users:
            text += f"ID: {u.id} | Имя: {u.name} | VK ID: {u.vk_id}\n"
        await event.answer(text)

# ---------- Run bot ----------
async def start_vk_bot():
    bot.labeler.load(bp)
    # Используем run_polling без создания нового event loop
    await bot.run_polling()
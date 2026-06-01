import json
from vkbottle.bot import BotLabeler, Message
from vkbottle import Keyboard, KeyboardButtonColor, Text

from database.connection import async_session
from services import user_service
from vk_bot.loader import vk_bot
from vk_bot.states import VkRegistrationStates

vk_registration_labeler = BotLabeler()


def get_vk_role_kb() -> str:
    kb = Keyboard(one_time=True, inline=True)
    kb.add(Text("👨‍🎓 Студент", payload={"role": "student"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Text("👨‍🏫 Преподаватель", payload={"role": "teacher"}), color=KeyboardButtonColor.PRIMARY)
    return kb.get_json()


def get_vk_format_kb() -> str:
    kb = Keyboard(one_time=True, inline=True)
    kb.add(Text("📝 Текст", payload={"format": "text"}), color=KeyboardButtonColor.SECONDARY)
    kb.add(Text("🖼️ Картинка", payload={"format": "image"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def get_vk_notif_kb() -> str:
    kb = Keyboard(one_time=True, inline=True)
    kb.add(Text("🔔 Включить", payload={"notif": 1}), color=KeyboardButtonColor.POSITIVE)
    kb.add(Text("🔕 Выключить", payload={"notif": 0}), color=KeyboardButtonColor.NEGATIVE)
    return kb.get_json()


@vk_registration_labeler.message(text=["Начать", "Start", "/start"])
async def vk_cmd_start(message: Message):
    async with async_session() as session:
        user = await user_service.get_user_by_platform_id(session, "vk", message.from_id)
        if not user:
            await user_service.create_user(session, "vk", message.from_id)

    await vk_bot.state_dispenser.set(message.from_id, VkRegistrationStates.WAITING_FOR_ROLE)
    await message.answer(
        "Привет! Добро пожаловать в ВК-версию бота расписания.\n"
        "Пожалуйста, выбери свою роль:",
        keyboard=get_vk_role_kb()
    )


# --- СТУДЕНТ ВК ---

@vk_registration_labeler.message(
    state=VkRegistrationStates.WAITING_FOR_ROLE,
    func=lambda msg: msg.payload is not None and json.loads(msg.payload).get("role") == "student"
)
async def vk_process_student_role(message: Message):
    async with async_session() as session:
        groups = await user_service.get_all_groups(session)

    if not groups:
        await message.answer("В базе данных нет групп.")
        await vk_bot.state_dispenser.delete(message.from_id)
        return

    kb = Keyboard(one_time=True, inline=True)
    for idx, g in enumerate(groups):
        if idx > 0 and idx % 3 == 0:
            kb.row()
        kb.add(Text(g.name, payload={"group_id": g.id}), color=KeyboardButtonColor.PRIMARY)

    await vk_bot.state_dispenser.set(message.from_id, VkRegistrationStates.WAITING_FOR_GROUP)
    await message.answer("Выбери свою учебную группу:", keyboard=kb.get_json())


@vk_registration_labeler.message(
    state=VkRegistrationStates.WAITING_FOR_GROUP,
    func=lambda msg: msg.payload is not None and "group_id" in json.loads(msg.payload)
)
async def vk_process_student_group(message: Message):
    payload = json.loads(message.payload)
    # Сохраняем group_id в состоянии
    await vk_bot.state_dispenser.set(
        message.from_id,
        VkRegistrationStates.WAITING_FOR_FORMAT,
        payload={"group_id": payload["group_id"]}
    )
    await message.answer("В каком виде присылать пары?", keyboard=get_vk_format_kb())


@vk_registration_labeler.message(
    state=VkRegistrationStates.WAITING_FOR_FORMAT,
    func=lambda msg: msg.payload is not None and "format" in json.loads(msg.payload)
)
async def vk_process_student_format(message: Message):
    payload = json.loads(message.payload)
    # Получаем текущий payload состояния
    state_data = message.state_peer.payload  # В vkbottle состояние хранится в message.state_peer
    if not state_data:
        state_data = {}
    state_data["schedule_format"] = payload["format"]  # 'text' или 'image'

    await vk_bot.state_dispenser.set(
        message.from_id,
        VkRegistrationStates.WAITING_FOR_NOTIFICATIONS,
        payload=state_data
    )
    await message.answer("Включить утренние уведомления?", keyboard=get_vk_notif_kb())


@vk_registration_labeler.message(
    state=VkRegistrationStates.WAITING_FOR_NOTIFICATIONS,
    func=lambda msg: msg.payload is not None and "notif" in json.loads(msg.payload)
)
async def vk_process_student_final(message: Message):
    payload = json.loads(message.payload)
    state_data = message.state_peer.payload
    if not state_data:
        await message.answer("Ошибка: данные регистрации потеряны. Начните заново с /start")
        return

    group_id = state_data.get("group_id")
    schedule_format = state_data.get("schedule_format", "text")  # 'text' или 'image'
    notif_enabled = bool(payload["notif"])

    # Преобразуем schedule_format в формат БД: 'image' -> 'pic', 'text' -> 'text'
    db_format = "pic" if schedule_format == "image" else "text"

    await vk_bot.state_dispenser.delete(message.from_id)

    async with async_session() as session:
        user = await user_service.get_user_by_platform_id(session, "vk", message.from_id)
        if user:
            # Привязываем группу
            success = await user_service.set_user_group(session, user.id, group_id)
            if not success:
                await message.answer("❌ Ошибка: группа не найдена. Попробуйте снова /start")
                return
            # Обновляем настройки
            await user_service.update_user_preferences(
                session, user.id,
                schedule_type=db_format,
                is_notification_on=notif_enabled
            )

    await message.answer("🎉 Регистрация в ВК успешно пройдена! Напишите /menu для начала работы.")


# --- ПРЕПОДАВАТЕЛЬ ВК ---

@vk_registration_labeler.message(
    state=VkRegistrationStates.WAITING_FOR_ROLE,
    func=lambda msg: msg.payload is not None and json.loads(msg.payload).get("role") == "teacher"
)
async def vk_process_teacher_role(message: Message):
    await vk_bot.state_dispenser.set(message.from_id, VkRegistrationStates.WAITING_FOR_TEACHER_NAME)
    await message.answer("Введите Ваши официальные ФИО (например: Баянова О.В.):")


@vk_registration_labeler.message(state=VkRegistrationStates.WAITING_FOR_TEACHER_NAME)
async def vk_process_teacher_name(message: Message):
    teacher_name = message.text.strip()
    await vk_bot.state_dispenser.delete(message.from_id)

    async with async_session() as session:
        user = await user_service.get_user_by_platform_id(session, "vk", message.from_id)
        if user:
            await user_service.create_teacher_request(session, user.id, teacher_name)

    await message.answer(
        f"Спасибо! Заявка для преподавателя ({teacher_name}) отправлена на модерацию админам ВК."
    )
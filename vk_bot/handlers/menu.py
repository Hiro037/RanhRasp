import json
from datetime import datetime, timedelta, date
from vkbottle.bot import BotLabeler, Message
from vkbottle import PhotoMessageUploader  # Загрузчик картинок в сообщения vkbottle

from database.connection import async_session
from services import user_service, schedule_service
from vk_bot import keyboards as kb
from config import settings
from utils.timezone import get_now
from utils.image_generator import generate_schedule_image

vk_menu_labeler = BotLabeler()
# Инициализируем загрузчик фото для ВК (потребует API бота)
from vk_bot.loader import vk_bot

photo_uploader = PhotoMessageUploader(vk_bot.api)


@vk_menu_labeler.message(text=["/menu", "Меню", "назад"])
@vk_menu_labeler.message(func=lambda msg: msg.payload is not None and json.loads(msg.payload).get("menu") == "back")
async def vk_show_main_menu(message: Message):
    """Вывод главного меню ВКонтакте."""
    is_admin = message.from_id in settings.VK_ADMINS
    await message.answer(
        "👋 Главное меню расписания филиала РАНХиГС (ВК):\n"
        "Выберите нужный пункт ниже:",
        keyboard=kb.get_vk_inline_main_menu(is_admin)
    )


@vk_menu_labeler.message(func=lambda msg: msg.payload is not None and json.loads(msg.payload).get("menu") == "schedule")
async def vk_initial_schedule(message: Message):
    """Первое открытие расписания по кнопке из меню."""
    today = get_now().date()
    await vk_send_schedule_core(message, today)


@vk_menu_labeler.message(func=lambda msg: msg.payload is not None and "vk_nav" in json.loads(msg.payload))
async def vk_schedule_navigation(message: Message):
    """Листание расписания кнопками пагинации в ВК."""
    payload_val = json.loads(message.payload)["vk_nav"]
    action, current_date_str = payload_val.split(":")
    current_date = datetime.strptime(current_date_str, "%Y-%m-%d").date()

    if action == "prev":
        target_date = current_date - timedelta(days=1)
    elif action == "next":
        target_date = current_date + timedelta(days=1)
    else:
        target_date = current_date

    await vk_send_schedule_core(message, target_date)


async def vk_send_schedule_core(message: Message, target_date: date):
    """
    Ядро отправки расписания для платформы ВКонтакте.
    Генерирует текст или загружает сгенерированные байты PNG на сервера VK.
    """
    async with async_session() as session:
        # 1. Получаем пользователя по VK ID
        user = await user_service.get_user_by_platform_id(session, "vk", message.from_id)
        if not user or not user.group_id:
            await message.answer("⚠️ Сначала зарегистрируйтесь, написав команду 'Начать' или '/start'.")
            return

        # 2. Извлекаем имя группы для отправки в шаблон
        group_name = "Неизвестная группа"
        if hasattr(user, "group") and user.group:
            group_name = user.group.name
        else:
            group = await user_service.get_group_by_id(session, user.group_id)
            if group:
                group_name = group.name

        # 3. Получаем список уроков и статус будущих дней
        lessons = await schedule_service.get_lessons_for_student(session, user.group_id, target_date)
        has_next = await schedule_service.has_lessons_future(session, target_date, group_id=user.group_id)

        # Генерируем json-клавиатуру для ВК
        vk_keyboard = kb.get_vk_schedule_keyboard(target_date, has_next)
        date_str = target_date.strftime("%d.%m.%Y")

        # 4. ЕСЛИ ВЫБРАН ФОРМАТ КАРТИНКИ
        if user.schedule_message_type == "image":
            # Передаем lessons, дату и вычисленное строковое имя группы
            image_bytes = await generate_schedule_image(lessons, target_date, group_name)

            # Загружаем байты картинки в облако ВКонтакте через официальный uploader
            attachment = await photo_uploader.upload(
                file_source=image_bytes,
                peer_id=message.peer_id
            )

            # Отправляем сообщение с прикрепленной фотографией
            await message.answer(
                message=f"🖼️ Расписание на {date_str} для группы {group_name}",
                attachment=attachment,
                keyboard=vk_keyboard
            )

        # 5. ЕСЛИ ВЫБРАН ТЕКСТОВЫЙ ФОРМАТ
        else:
            text = f"📅 Расписание на {date_str} | Группа: {group_name}\n\n"
            if not lessons:
                text += "💤 В этот день занятий нет. Отдыхайте!"
            else:
                for idx, lesson in enumerate(lessons, 1):
                    time_start = lesson.start_datetime.strftime("%H:%M")
                    teacher = lesson.teacher.name if lesson.teacher else "Не указан"
                    text += f"{idx}. {time_start} — {lesson.subject.name}\n"
                    text += f"🏫 Ауд: {lesson.classroom.name} | 👤 {teacher} ({lesson.type})\n"
                    if lesson.comment:
                        text += f"📝 Заметка: {lesson.comment}\n"
                    text += "\n"

            await message.answer(message=text, keyboard=vk_keyboard)
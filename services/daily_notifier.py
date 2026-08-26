"""
Ежедневная рассылка расписания на текущий день пользователям с is_notification_on = True
Запускается по расписанию из main.py (например, каждый день в 8:00 по местному времени)
"""

import asyncio
import logging
from datetime import date
from html import escape as html_escape
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import async_session
from database.models import User, Teacher
from services import user_service, schedule_service
from utils.timezone import get_now, YEKT_TZ
from utils.image_generator import generate_schedule_image
from config import settings

# Импортируем ботов (для отправки сообщений)
from tg_bot.loader import tg_bot
from vk_bot.loader import vk_bot
from vkbottle import PhotoMessageUploader

# Загружаем утилиту для загрузки фото в VK (создаём один раз)
vk_photo_uploader = PhotoMessageUploader(vk_bot.api)

logger = logging.getLogger(__name__)


async def get_user_schedule_data(user: User, target_date: date, session: AsyncSession):
    """
    Возвращает список занятий для пользователя на указанную дату,
    а также группу/преподавателя для формирования текста.
    """
    # Определяем роль
    role = await user_service.determine_user_role(user)

    if role == "student":
        if not user.groups:
            return None, None, None
        group = user.groups[0]
        lessons = await schedule_service.get_lessons_for_student(session, group.id, target_date)
        entity_name = group.name
    elif role == "teacher" and user.teacher_profile_id:
        lessons = await schedule_service.get_lessons_for_teacher(session, user.teacher_profile_id, target_date)
        teacher = await session.get(Teacher, user.teacher_profile_id)
        entity_name = teacher.name if teacher else "Преподаватель"
    else:
        return None, None, None

    return lessons, entity_name, role


async def send_daily_notification_to_user(user: User, target_date: date):
    """Отправляет одно уведомление конкретному пользователю."""
    async with async_session() as session:
        lessons, entity_name, role = await get_user_schedule_data(user, target_date, session)

    if lessons is None:
        # Не удалось определить данные (нет группы у студента или нет профиля у преподавателя)
        logger.info("Пропуск пользователя %s: не определены группа/профиль преподавателя", user.id)
        return

    date_str = target_date.strftime("%d.%m.%Y")
    if not lessons:
        text_tg = f"🔔 <b>Доброе утро!</b>\n\n📅 Сегодня {date_str} занятий нет. Хорошего дня!"
        text_vk = f"🔔 Доброе утро!\n\n📅 Сегодня {date_str} занятий нет. Хорошего дня!"
        # Отправляем только текст (не картинку, т.к. занятий нет)
        await _send_message(user, text_tg, text_vk, None)
        return

    # Формируем текст или картинку в зависимости от настроек пользователя
    if user.schedule_message_type == "text":
        await _send_message(
            user,
            _format_lessons_text(lessons, entity_name, date_str),
            _format_lessons_text_vk(lessons, entity_name, date_str),
            None,
        )
    else:  # "pic"
        try:
            image_bytes = await generate_schedule_image(lessons, target_date, entity_name)
            await _send_message(user, None, None, image_bytes)
        except Exception as e:
            # Если не удалось сгенерировать картинку – отправляем текст как fallback
            await _send_message(
                user,
                _format_lessons_text(lessons, entity_name, date_str),
                _format_lessons_text_vk(lessons, entity_name, date_str),
                None,
            )
            logger.error("Ошибка генерации картинки для user %s: %s", user.id, e)


def _format_lessons_text(lessons, entity_name: str, date_str: str) -> str:
    """Форматирует расписание в текстовый вид (HTML с экранированием данных из БД)."""
    text = "🔔 <b>Доброе утро!</b>\n\n📅 <b>Расписание на %s</b>" % date_str
    if entity_name:
        text += "\n👥 <b>%s</b>" % html_escape(str(entity_name))
    text += "\n\n"
    for idx, lesson in enumerate(lessons, 1):
        time_start = lesson.start_datetime.astimezone(YEKT_TZ).strftime("%H:%M")
        subject = html_escape(lesson.subject.name) if lesson.subject else "—"
        teacher = html_escape(lesson.teacher.name) if lesson.teacher else "Не указан"
        classroom = html_escape(lesson.classroom.name) if lesson.classroom else "—"
        lesson_type = html_escape(lesson.type)
        text += f"{idx}. <b>{time_start}</b> – {subject}\n"
        text += f"   🏫 {classroom} | 👤 {teacher} ({lesson_type})\n"
        if lesson.comment:
            text += f"   📝 <b>Заметка:</b> {html_escape(lesson.comment)}\n"
        text += "\n"
    return text


def _format_lessons_text_vk(lessons, entity_name: str, date_str: str) -> str:
    """Форматирует расписание для VK (обычный текст без HTML-тегов)."""
    text = f"🔔 Доброе утро!\n\n📅 Расписание на {date_str}"
    if entity_name:
        text += f"\n👥 {entity_name}"
    text += "\n\n"
    for idx, lesson in enumerate(lessons, 1):
        time_start = lesson.start_datetime.astimezone(YEKT_TZ).strftime("%H:%M")
        subject = lesson.subject.name if lesson.subject else "—"
        teacher = lesson.teacher.name if lesson.teacher else "Не указан"
        classroom = lesson.classroom.name if lesson.classroom else "—"
        text += f"{idx}. {time_start} – {subject}\n"
        text += f"   🏫 {classroom} | 👤 {teacher} ({lesson.type})\n"
        if lesson.comment:
            text += f"   📝 Заметка: {lesson.comment}\n"
        text += "\n"
    return text


async def _send_message(
    user: User,
    text_tg: Optional[str] = None,
    text_vk: Optional[str] = None,
    image_bytes: Optional[bytes] = None,
):
    """Отправляет сообщение пользователю на его платформу (текст для каждой платформы свой)."""
    try:
        if user.platform == "telegram":
            if image_bytes:
                from aiogram.types import BufferedInputFile
                photo = BufferedInputFile(image_bytes, filename="schedule.png")
                await tg_bot.send_photo(chat_id=user.platform_id, photo=photo, caption=text_tg, parse_mode="HTML")
            else:
                await tg_bot.send_message(chat_id=user.platform_id, text=text_tg, parse_mode="HTML")
        elif user.platform == "vk":
            if image_bytes:
                attachment = await vk_photo_uploader.upload(
                    file_source=image_bytes,
                    peer_id=user.platform_id
                )
                await vk_bot.api.messages.send(
                    peer_id=user.platform_id,
                    message=text_vk or "Расписание на сегодня",
                    attachment=attachment,
                    random_id=0
                )
            else:
                await vk_bot.api.messages.send(
                    peer_id=user.platform_id,
                    message=text_vk,
                    random_id=0
                )
    except Exception as e:
        logger.error("Ошибка отправки уведомления пользователю %s (%s): %s", user.id, user.platform, e)


async def send_daily_notifications():
    """
    Основная функция для планировщика.
    Отправляет уведомления всем пользователям с is_notification_on = True.
    """
    target_date = get_now().date()
    logger.info("[DailyNotifier] Запуск рассылки на %s", target_date)

    async with async_session() as session:
        # Получаем всех пользователей с включёнными уведомлениями
        stmt = select(User).where(User.is_notification_on == True)
        result = await session.execute(stmt)
        users = result.scalars().all()

    tasks = [send_daily_notification_to_user(user, target_date) for user in users]

    if tasks:
        # return_exceptions=True: сбой одному пользователю не отменяет рассылку остальным
        results = await asyncio.gather(*tasks, return_exceptions=True)
        errors = [r for r in results if isinstance(r, Exception)]
        if errors:
            logger.error("[DailyNotifier] Ошибок при рассылке: %d из %d", len(errors), len(tasks))
            for err in errors:
                logger.error("[DailyNotifier] %s", err)

    logger.info("[DailyNotifier] Рассылка завершена. Обработано %d пользователей.", len(tasks))

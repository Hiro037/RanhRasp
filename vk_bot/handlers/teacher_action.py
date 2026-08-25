import json
import asyncio
from datetime import datetime
from vkbottle.bot import BotLabeler, Message
from vkbottle import Keyboard, KeyboardButtonColor, Text
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database.connection import async_session
from database.models import Lesson
from services import user_service, schedule_service
from vk_bot.keyboards import get_vk_inline_main_menu
from vk_bot.states import VkTeacherStates
from vk_bot.loader import vk_bot
from utils.timezone import get_now, YEKT_TZ

from tg_bot.loader import tg_bot  # для отправки уведомлений в Telegram

vk_teacher_labeler = BotLabeler()


@vk_teacher_labeler.message(
    func=lambda msg: msg.payload is not None and "add_comment_for_date" in json.loads(msg.payload)
)
async def vk_show_lessons_for_comment(message: Message):
    """Показывает список занятий преподавателя на выбранную дату (VK)."""
    payload = json.loads(message.payload)
    date_str = payload["add_comment_for_date"]
    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()

    async with async_session() as session:
        user = await user_service.get_user_by_platform_id(session, "vk", message.from_id)
        if not user or user.teacher_profile_id is None:
            await message.answer("⚠️ У вас нет прав преподавателя.")
            return

        lessons = await schedule_service.get_lessons_for_teacher(session, user.teacher_profile_id, target_date)

    if not lessons:
        kb = Keyboard(inline=True)
        kb.add(Text("🔙 Назад к расписанию", payload={"vk_nav": f"refresh:{date_str}"}), color=KeyboardButtonColor.SECONDARY)
        kb.row()
        kb.add(Text("🏠 Главное меню", payload={"menu": "back"}), color=KeyboardButtonColor.SECONDARY)
        await message.answer(
            f"📅 На {target_date.strftime('%d.%m.%Y')} у вас нет занятий.\n\n"
            f"Вы можете добавить комментарий только к существующим парам.",
            keyboard=kb.get_json()
        )
        return

    kb = Keyboard(inline=True)
    for idx, lesson in enumerate(lessons):
        if idx > 0:
            kb.row()
        time_str = lesson.start_datetime.astimezone(YEKT_TZ).strftime("%H:%M")
        subject_name = lesson.subject.name if lesson.subject else "Без названия"
        btn_text = f"⏰ {time_str} | {subject_name[:20]}"
        kb.add(Text(btn_text, payload={"teach_comment_lesson": lesson.id, "return_date": date_str}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Text("🔙 Назад к расписанию", payload={"vk_nav": f"refresh:{date_str}"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Text("🏠 Главное меню", payload={"menu": "back"}), color=KeyboardButtonColor.SECONDARY)

    await message.answer(
        "✏️ Выберите занятие для добавления комментария:",
        keyboard=kb.get_json()
    )


@vk_teacher_labeler.message(
    func=lambda msg: msg.payload is not None and "teach_comment_lesson" in json.loads(msg.payload)
)
async def vk_prompt_comment_text(message: Message):
    """Переводит в состояние ожидания текста комментария."""
    payload = json.loads(message.payload)
    lesson_id = payload["teach_comment_lesson"]
    return_date = payload.get("return_date", "")

    await vk_bot.state_dispenser.set(
        message.from_id,
        VkTeacherStates.WAITING_FOR_COMMENT,
        payload={"lesson_id": lesson_id, "return_date": return_date}
    )

    kb = Keyboard(inline=True)
    kb.add(Text("❌ Отмена", payload={"cancel_comment": return_date}), color=KeyboardButtonColor.NEGATIVE)
    await message.answer(
        "📝 Введите текст комментария (домашнего задания) для студентов.\n\n"
        "Текст будет отправлен всем студентам, у которых есть это занятие.\n"
        "Для отмены нажмите кнопку ниже.",
        keyboard=kb.get_json()
    )


@vk_teacher_labeler.message(state=VkTeacherStates.WAITING_FOR_COMMENT)
async def vk_save_comment_and_notify(message: Message):
    """Сохраняет комментарий и запускает рассылку."""
    comment_text = message.text.strip()
    if not comment_text:
        await message.answer("❌ Комментарий не может быть пустым.")
        return

    state_data = message.state_peer.payload
    lesson_id = state_data["lesson_id"]
    return_date_str = state_data.get("return_date", "")

    await vk_bot.state_dispenser.delete(message.from_id)

    async with async_session() as session:
        stmt = select(Lesson).where(Lesson.id == lesson_id).options(
            selectinload(Lesson.subject), selectinload(Lesson.teacher)
        )
        res = await session.execute(stmt)
        lesson = res.scalars().first()

        if not lesson:
            await message.answer("❌ Ошибка: занятие не найдено.")
            return

        subject_name = lesson.subject.name if lesson.subject else "Без названия"
        start_time = lesson.start_datetime.astimezone(YEKT_TZ).strftime("%H:%M")
        teacher_name = lesson.teacher.name if lesson.teacher else "Преподаватель"

        await schedule_service.add_comment_to_lesson(session, lesson_id, comment_text)

    await message.answer(
        f"✅ Комментарий к занятию «{subject_name}» ({start_time}) сохранён!\n"
        f"Рассылка студентам запущена."
    )

    # Фоновая рассылка (та же функция, что и для Telegram)
    from vk_bot.handlers.teacher_action import send_notification_to_students  # избегаем циклического импорта
    asyncio.create_task(send_notification_to_students(
        lesson_id, subject_name, start_time, teacher_name, comment_text
    ))

    # Возврат к расписанию
    if return_date_str:
        from vk_bot.handlers.menu import vk_send_schedule_core
        await vk_send_schedule_core(message, datetime.strptime(return_date_str, "%Y-%m-%d").date())


@vk_teacher_labeler.message(func=lambda msg: msg.payload is not None and "cancel_comment" in json.loads(msg.payload))
async def vk_cancel_comment(message: Message):
    """Отмена добавления комментария."""
    payload = json.loads(message.payload)
    return_date_str = payload.get("cancel_comment", "")
    await vk_bot.state_dispenser.delete(message.from_id)
    if return_date_str:
        from vk_bot.handlers.menu import vk_send_schedule_core
        await vk_send_schedule_core(message, datetime.strptime(return_date_str, "%Y-%m-%d").date())
    else:
        await message.answer("❌ Отменено.", keyboard=get_vk_inline_main_menu(False))


async def send_notification_to_students(lesson_id: int, subject: str, time_str: str, teacher: str, comment: str):
    """Фоновая рассылка (кроссплатформенная) – дублируется из tg_bot, но можно вынести в общий сервис."""
    async with async_session() as session:
        recipients = await schedule_service.get_students_for_lesson_notification(session, lesson_id)

    text_tg = (
        f"🔔 *Новый комментарий преподавателя!*\n\n"
        f"📖 *Предмет:* {subject}\n"
        f"👨‍🏫 *Преподаватель:* {teacher}\n"
        f"⏰ *Время:* {time_str}\n\n"
        f"📝 *Комментарий:*\n_{comment}_"
    )
    text_vk = (
        f"🔔 Новый комментарий преподавателя!\n\n"
        f"📖 Предмет: {subject}\n"
        f"👨‍🏫 Преподаватель: {teacher}\n"
        f"⏰ Время: {time_str}\n\n"
        f"📝 Комментарий:\n{comment}"
    )

    for student in recipients:
        if not student.is_notification_on:
            continue
        try:
            if student.platform == "telegram":
                await tg_bot.send_message(chat_id=student.platform_id, text=text_tg, parse_mode="Markdown")
            elif student.platform == "vk":
                await vk_bot.api.messages.send(peer_id=student.platform_id, message=text_vk, random_id=0)
        except Exception as e:
            print(f"Уведомление не доставлено студенту {student.id} ({student.platform}): {e}")
        await asyncio.sleep(0.05)
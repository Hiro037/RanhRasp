import json
import asyncio
from vkbottle.bot import BotLabeler, Message
from vkbottle import Keyboard, KeyboardButtonColor, Text
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database.connection import async_session_maker
from database.models import Lesson
from services import user_service, schedule_service
from vk_bot.states import VkTeacherStates
from vk_bot.loader import vk_bot

# Переиспользуем асинхронную таску рассылки из TG хендлера для чистой архитектуры DRY
from tg_bot.handlers.teacher_action import send_notification_to_students
from utils.timezone import get_now

vk_teacher_labeler = BotLabeler()


@vk_teacher_labeler.message(
    func=lambda msg: msg.payload is not None and json.loads(msg.payload).get("menu") == "teacher_panel")
async def vk_btn_add_comment(message: Message):
    """Вывод списка пар для учителя внутри ВКонтакте."""
    today = get_now().date()

    async with async_session_maker() as session:
        user = await user_service.get_user_by_platform_id(session, "vk", message.from_id)
        if not user or user.role != "teacher" or not user.teacher_id:
            await message.answer("⚠️ У вас нет прав доступа к панели преподавателя.")
            return

        # Твой сервис
        lessons = await schedule_service.get_lessons_for_teacher(session, user.teacher_id, today)

    if not lessons:
        kb = Keyboard(inline=True).add(Text("🔙 Назад", payload={"menu": "back"}), color=KeyboardButtonColor.SECONDARY)
        await message.answer(f"📅 На сегодня ({today.strftime('%d.%m.%Y')}) пар не запланировано.",
                             keyboard=kb.get_json())
        return

    kb = Keyboard(inline=True)
    for idx, lesson in enumerate(lessons):
        if idx > 0:
            kb.row()
        time_str = lesson.start_datetime.strftime("%H:%M")
        subject_name = lesson.subject.name if lesson.subject else "Без названия"
        btn_text = f"⏰ {time_str} | {subject_name[:15]}"
        kb.add(Text(btn_text, payload={"teach_cls": lesson.id}), color=KeyboardButtonColor.PRIMARY)

    kb.row()
    kb.add(Text("🔙 Главное меню", payload={"menu": "back"}), color=KeyboardButtonColor.SECONDARY)

    await message.answer("📝 Выберите занятие для добавления заметок/ДЗ студентам:", keyboard=kb.get_json())


@vk_teacher_labeler.message(func=lambda msg: msg.payload is not None and "teach_cls" in json.loads(msg.payload))
async def vk_process_lesson_selection(message: Message):
    """Переключение состояния FSM vkbottle."""
    lesson_id = json.loads(message.payload)["teach_cls"]

    await vk_bot.state_dispenser.set(
        message.from_id,
        VkTeacherStates.WAITING_FOR_COMMENT,
        payload={"lesson_id": lesson_id}
    )
    await message.answer("📥 Напишите текст комментария или домашнего задания:")


@vk_teacher_labeler.message(state=VkTeacherStates.WAITING_FOR_COMMENT)
async def vk_save_comment_and_notify(message: Message):
    """Сохранение и вызов кроссплатформенного уведомления."""
    comment_text = message.text.strip()
    state_data = message.state_peer.payload
    lesson_id = state_data["lesson_id"]

    await vk_bot.state_dispenser.delete(message.from_id)

    async with async_session_maker() as session:
        # Предварительно берем метаданные для генерации текста сообщения
        stmt = select(Lesson).where(Lesson.id == lesson_id).options(selectinload(Lesson.subject))
        res = await session.execute(stmt)
        lesson = res.scalars().first()

        if not lesson:
            await message.answer("❌ Занятие не найдено.")
            return

        subject_name = lesson.subject.name if lesson.subject else "Без названия"
        start_time = lesson.start_datetime.strftime("%H:%M")

        # Твой метод изменения данных в СУБД
        await schedule_service.add_comment_to_lesson(session, lesson_id, comment_text)

    await message.answer("✅ Комментарий сохранен! Студенты получат уведомления.")

    # Запускаем фоновую задачу рассылки
    asyncio.create_task(send_notification_to_students(lesson_id, subject_name, start_time, comment_text))

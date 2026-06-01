import json
import asyncio
from vkbottle.bot import BotLabeler, Message
from vkbottle import Keyboard, KeyboardButtonColor, Text
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database.connection import async_session
from database.models import Lesson
from services import user_service, schedule_service
from vk_bot.states import VkTeacherStates
from vk_bot.loader import vk_bot
from utils.timezone import get_now

# Переиспользуем общую функцию рассылки из telegram (она не зависит от платформы)
# Но для VK нужна своя адаптация – сделаем отдельную, но с общей логикой
# Чтобы не дублировать, создадим отдельный сервис уведомлений, но для простоты скопируем логику
from tg_bot.loader import tg_bot  # для отправки в Telegram

vk_teacher_labeler = BotLabeler()


@vk_teacher_labeler.message(
    func=lambda msg: msg.payload is not None and json.loads(msg.payload).get("menu") == "teacher_panel"
)
async def vk_btn_add_comment(message: Message):
    """Вывод списка пар для учителя внутри ВКонтакте."""
    today = get_now().date()

    async with async_session() as session:
        user = await user_service.get_user_by_platform_id(session, "vk", message.from_id)
        if not user or user.teacher_profile_id is None:
            await message.answer("⚠️ У вас нет прав доступа к панели преподавателя.")
            return

        lessons = await schedule_service.get_lessons_for_teacher(session, user.teacher_profile_id, today)

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

    async with async_session() as session:
        stmt = select(Lesson).where(Lesson.id == lesson_id).options(selectinload(Lesson.subject))
        res = await session.execute(stmt)
        lesson = res.scalars().first()

        if not lesson:
            await message.answer("❌ Занятие не найдено.")
            return

        subject_name = lesson.subject.name if lesson.subject else "Без названия"
        start_time = lesson.start_datetime.strftime("%H:%M")

        await schedule_service.add_comment_to_lesson(session, lesson_id, comment_text)

    await message.answer("✅ Комментарий сохранен! Студенты получат уведомления.")

    # Запускаем фоновую рассылку
    asyncio.create_task(send_notification_to_students_vk(lesson_id, subject_name, start_time, comment_text))


async def send_notification_to_students_vk(lesson_id: int, subject: str, time_str: str, comment: str):
    """Фоновая рассылка студентам (и в VK, и в Telegram) с использованием общей логики."""
    async with async_session() as session:
        recipients = await schedule_service.get_students_for_lesson_notification(session, lesson_id)

    text_tg = (
        f"🔔 *Важное уведомление от преподавателя!*\n\n"
        f"📖 Предмет: *{subject}*\n"
        f"⏰ Время: *{time_str}*\n"
        f"📝 Комментарий: _{comment}_"
    )
    text_vk = f"🔔 Важное уведомление от преподавателя!\n\n📖 Предмет: {subject}\n⏰ Время: {time_str}\n📝 Комментарий: {comment}"

    for student in recipients:
        if not student.is_notification_on:
            continue
        try:
            if student.platform == "telegram":
                await tg_bot.send_message(chat_id=student.platform_id, text=text_tg, parse_mode="Markdown")
            elif student.platform == "vk":
                await vk_bot.api.messages.send(peer_id=student.platform_id, message=text_vk, random_id=0)
        except Exception as e:
            print(f"Не удалось отправить уведомление пользователю {student.id} (platform={student.platform}): {e}")
        await asyncio.sleep(0.04)

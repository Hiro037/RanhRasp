import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database.connection import async_session
from database.models import Lesson, User
from services import user_service, schedule_service
from tg_bot.states import TeacherActionStates
from utils.timezone import get_now

# Импорты ботов для отправки уведомлений (из правильных модулей)
from tg_bot.loader import tg_bot
from vk_bot.loader import vk_bot

teacher_router = Router()


@teacher_router.callback_query(F.data == "menu:teacher_panel")
async def btn_add_comment(callback: CallbackQuery):
    today = get_now().date()

    async with async_session() as session:
        user = await user_service.get_user_by_platform_id(session, "telegram", callback.from_user.id)

        # Проверка прав: преподаватель и привязан к teacher_profile_id
        if not user or user.teacher_profile_id is None:
            await callback.answer("⚠️ У вас нет доступа к панели преподавателя.", show_alert=True)
            return

        # Получаем занятия преподавателя на сегодня
        lessons = await schedule_service.get_lessons_for_teacher(session, user.teacher_profile_id, today)

    if not lessons:
        await callback.message.edit_text(
            f"📅 На сегодня ({today.strftime('%d.%m.%Y')}) у вас нет запланированных занятий.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="menu:back")]
            ])
        )
        await callback.answer()
        return

    builder = InlineKeyboardBuilder()
    for lesson in lessons:
        time_str = lesson.start_datetime.strftime("%H:%M")
        subject_name = lesson.subject.name if lesson.subject else "Без названия"
        btn_text = f"⏰ {time_str} | {subject_name[:20]}"
        builder.button(text=btn_text, callback_data=f"teach_cls:{lesson.id}")

    builder.button(text="🔙 Главное меню", callback_data="menu:back")
    builder.adjust(1)

    await callback.message.edit_text(
        "📝 Выберите занятие, к которому хотите добавить/обновить комментарий или домашнее задание:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@teacher_router.callback_query(F.data.startswith("teach_cls:"))
async def process_lesson_selection(callback: CallbackQuery, state: FSMContext):
    lesson_id = int(callback.data.split(":")[1])

    await state.set_state(TeacherActionStates.waiting_for_comment)
    await state.update_data(lesson_id=lesson_id)

    await callback.message.edit_text(
        "📥 Введите текст комментария (задания) для студентов.\n"
        "После отправки система автоматически уведомит все группы на этой паре."
    )
    await callback.answer()


@teacher_router.message(TeacherActionStates.waiting_for_comment)
async def save_comment_and_notify(message: Message, state: FSMContext):
    comment_text = message.text.strip()
    state_data = await state.get_data()
    lesson_id = state_data["lesson_id"]
    await state.clear()

    async with async_session() as session:
        # Получаем урок с подгрузкой предмета
        stmt = select(Lesson).where(Lesson.id == lesson_id).options(selectinload(Lesson.subject))
        res = await session.execute(stmt)
        lesson = res.scalars().first()

        if not lesson:
            await message.answer("❌ Ошибка: занятие не найдено в базе данных.")
            return

        subject_name = lesson.subject.name if lesson.subject else "Без названия"
        start_time = lesson.start_datetime.strftime("%H:%M")

        # Сохраняем комментарий
        await schedule_service.add_comment_to_lesson(session, lesson_id, comment_text)

    await message.answer("✅ Комментарий сохранен! Запущена фоновая кроссплатформенная рассылка.")

    # Запускаем фоновую рассылку
    asyncio.create_task(send_notification_to_students(lesson_id, subject_name, start_time, comment_text))


async def send_notification_to_students(lesson_id: int, subject: str, time_str: str, comment: str):
    """Фоновая рассылка студентам, привязанным к группам этого занятия."""
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
        # Проверяем, включены ли у студента уведомления
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
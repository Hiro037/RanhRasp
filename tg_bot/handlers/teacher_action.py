import asyncio
from datetime import datetime

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database.connection import async_session
from database.models import Lesson
from services import user_service, schedule_service
from tg_bot.states import TeacherActionStates
from utils.timezone import get_now, YEKT_TZ

from tg_bot.loader import tg_bot
from vk_bot.loader import vk_bot

teacher_router = Router()


@teacher_router.callback_query(F.data.startswith("add_comment_for_date:"))
async def show_lessons_for_comment(callback: CallbackQuery):
    """Показывает список занятий преподавателя на выбранную дату."""
    date_str = callback.data.split(":")[1]
    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()

    async with async_session() as session:
        user = await user_service.get_user_by_platform_id(session, "telegram", callback.from_user.id)
        if not user or user.teacher_profile_id is None:
            await callback.answer("⚠️ У вас нет прав преподавателя.", show_alert=True)
            return

        lessons = await schedule_service.get_lessons_for_teacher(session, user.teacher_profile_id, target_date)

    if not lessons:
        await callback.message.edit_text(
            f"📅 На {target_date.strftime('%d.%m.%Y')} у вас нет занятий.\n\n"
            "Вы можете добавить комментарий только к существующим парам.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад к расписанию", callback_data=f"sched_nav:refresh:{date_str}")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:back")]
            ])
        )
        await callback.answer()
        return

    builder = InlineKeyboardBuilder()
    for lesson in lessons:
        time_str = lesson.start_datetime.astimezone(YEKT_TZ).strftime("%H:%M")
        subject_name = lesson.subject.name if lesson.subject else "Без названия"
        btn_text = f"⏰ {time_str} | {subject_name[:25]}"
        builder.button(text=btn_text, callback_data=f"teach_comment_lesson:{lesson.id}:{date_str}")
    builder.button(text="🔙 Назад к расписанию", callback_data=f"sched_nav:refresh:{date_str}")
    builder.button(text="🏠 Главное меню", callback_data="menu:back")
    builder.adjust(1)

    await callback.message.edit_text(
        "✏️ Выберите занятие, к которому хотите добавить или изменить комментарий:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@teacher_router.callback_query(F.data.startswith("teach_comment_lesson:"))
async def prompt_comment_text(callback: CallbackQuery, state: FSMContext):
    """Запрашивает текст комментария для выбранного занятия."""
    _, lesson_id, date_str = callback.data.split(":")
    lesson_id = int(lesson_id)

    await state.set_state(TeacherActionStates.waiting_for_comment)
    await state.update_data(lesson_id=lesson_id, return_date=date_str)

    await callback.message.edit_text(
        "📝 Введите текст комментария (домашнего задания, важной информации) для студентов.\n\n"
        "Текст будет отправлен **всем студентам**, у которых есть это занятие в расписании.\n"
        "Чтобы отменить, отправьте /cancel.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data=f"sched_nav:refresh:{date_str}")]
        ])
    )
    await callback.answer()


@teacher_router.message(TeacherActionStates.waiting_for_comment)
async def save_comment_and_notify(message: Message, state: FSMContext):
    """Сохраняет комментарий и запускает рассылку студентам."""
    comment_text = message.text.strip()
    if not comment_text:
        await message.answer("❌ Комментарий не может быть пустым. Попробуйте снова.")
        return

    state_data = await state.get_data()
    lesson_id = state_data["lesson_id"]
    return_date_str = state_data.get("return_date")
    await state.clear()

    async with async_session() as session:
        # Получаем занятие с подгрузкой связей
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

        # Сохраняем комментарий
        await schedule_service.add_comment_to_lesson(session, lesson_id, comment_text)

    await message.answer(
        f"✅ Комментарий к занятию **{subject_name}** ({start_time}) сохранён!\n"
        f"Запущена рассылка студентам...",
        parse_mode="Markdown"
    )

    # Фоновая рассылка
    asyncio.create_task(send_notification_to_students(
        lesson_id, subject_name, start_time, teacher_name, comment_text
    ))

    # Возвращаем пользователя к расписанию на ту же дату
    if return_date_str:
        from tg_bot.handlers.menu import send_schedule
        # Имитируем callback для обновления расписания
        await send_schedule(message, message.from_user.id, datetime.strptime(return_date_str, "%Y-%m-%d").date(), edit_mode=False)


async def send_notification_to_students(lesson_id: int, subject: str, time_str: str, teacher: str, comment: str):
    """Фоновая рассылка студентам (кроссплатформенная)."""
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
            print(f"Не удалось отправить уведомление студенту {student.id} ({student.platform}): {e}")
        await asyncio.sleep(0.05)  # небольшая задержка, чтобы не спамить

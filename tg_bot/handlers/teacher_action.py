import asyncio
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
from utils.timezone import get_now

# Импорты инстансов ботов для кроссплатформенной фоновой рассылки
from tg_bot.loader import tg_bot
from vk_bot.loader import vk_bot

teacher_router = Router()


@teacher_router.callback_query(F.data == "menu:teacher_panel")
async def btn_add_comment(callback: CallbackQuery):
    """Выводит список занятий преподавателя на сегодня для выбора."""
    today = get_now().date()

    async with async_session_maker() as session:
        user = await user_service.get_user_by_platform_id(session, "tg", callback.from_user.id)

        if not user or user.role != "teacher" or not user.teacher_id:
            await callback.answer("⚠️ У вас нет доступа к панели преподавателя.", show_alert=True)
            return

        # Используем твою функцию из schedule_service
        lessons = await schedule_service.get_lessons_for_teacher(session, user.teacher_id, today)

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
        # Безопасно получаем имя предмета (учитывая связь)
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
    """Включение FSM и сохранение ID выбранной пары."""
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
    """Сохранение комментария через твой сервис и запуск фоновой рассылки."""
    comment_text = message.text.strip()
    state_data = await state.get_data()
    lesson_id = state_data["lesson_id"]
    await state.clear()

    async with async_session_maker() as session:
        # Так как твоя add_comment_to_lesson возвращает None, мы сначала
        # подтянем данные урока для красивого текста уведомления (предмет и время)
        stmt = select(Lesson).where(Lesson.id == lesson_id).options(selectinload(Lesson.subject))
        res = await session.execute(stmt)
        lesson = res.scalars().first()

        if not lesson:
            await message.answer("❌ Ошибка: занятие не найдено в базе данных.")
            return

        subject_name = lesson.subject.name if lesson.subject else "Без названия"
        start_time = lesson.start_datetime.strftime("%H:%M")

        # Вызываем твою функцию (она сама сделает коммит внутренее)
        await schedule_service.add_comment_to_lesson(session, lesson_id, comment_text)

    await message.answer("✅ Комментарий сохранен! Запущена фоновая кроссплатформенная рассылка.")

    # Запускаем фоновую задачу (не блокируя хендлер)
    asyncio.create_task(send_notification_to_students(lesson_id, subject_name, start_time, comment_text))


async def send_notification_to_students(lesson_id: int, subject: str, time_str: str, comment: str):
    """Фоновая рассылка студентам на основе твоей функции выборки."""
    async with async_session_maker() as session:
        # Вызов твоей точной функции поиска студентов
        recipients = await schedule_service.get_students_to_notify_by_lesson(session, lesson_id)

    text_tg = (
        f"🔔 *Важное уведомление от преподавателя!*\n\n"
        f"📖 Предмет: *{subject}*\n"
        f"⏰ Время: *{time_str}*\n"
        f"📝 Комментарий: _{comment}_"
    )
    text_vk = f"🔔 Важное уведомление от преподавателя!\n\n📖 Предмет: {subject}\n⏰ Время: {time_str}\n📝 Комментарий: {comment}"

    for student in recipients:
        # Проверяем, включены ли у студента уведомления в настройках профиля
        if not student.notifications_enabled:
            continue

        try:
            # Мапим отправку в зависимости от заполненных ID платформ в модели User
            if hasattr(student, "tg_id") and student.tg_id:
                await tg_bot.send_message(chat_id=student.tg_id, text=text_tg, parse_mode="Markdown")
            elif hasattr(student, "vk_id") and student.vk_id:
                await vk_bot.api.messages.send(peer_id=student.vk_id, message=text_vk, random_id=0)

            # Тайм-аут во избежание флуд-контроля API мессенджеров
            await asyncio.sleep(0.04)
        except Exception as e:
            print(f"Не удалось отправить уведомление пользователю {student.id}: {e}")

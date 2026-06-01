from datetime import datetime, timedelta, date
from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from sqlalchemy.orm import selectinload

from database.connection import async_session
from services import user_service, schedule_service
from tg_bot import keyboards as kb
from config import settings
from utils.timezone import get_now
from utils.image_generator import generate_schedule_image

menu_router = Router()


@menu_router.message(Command("menu"))
async def show_main_menu(message: Message):
    is_admin = message.from_user.id in settings.TG_ADMINS
    await message.answer(
        "👋 Вы находитесь в главном меню системы расписания.\n"
        "Выберите интересующий вас раздел:",
        reply_markup=kb.get_inline_main_menu(is_admin)
    )


@menu_router.callback_query(F.data == "menu:back")
async def callback_back_to_menu(callback: CallbackQuery):
    is_admin = callback.from_user.id in settings.TG_ADMINS
    await callback.message.edit_text(
        "👋 Вы находитесь в главном меню системы расписания.\n"
        "Выберите интересующий вас раздел:",
        reply_markup=kb.get_inline_main_menu(is_admin)
    )
    await callback.answer()


@menu_router.callback_query(F.data == "menu:schedule")
async def callback_show_initial_schedule(callback: CallbackQuery):
    today = get_now().date()
    await send_schedule(callback, callback.from_user.id, today, edit_mode=False)
    await callback.message.delete()
    await callback.answer()


@menu_router.callback_query(F.data.startswith("sched_nav:"))
async def handle_schedule_navigation(callback: CallbackQuery):
    _, action, current_date_str = callback.data.split(":")
    current_date = datetime.strptime(current_date_str, "%Y-%m-%d").date()

    if action == "prev":
        target_date = current_date - timedelta(days=1)
    elif action == "next":
        target_date = current_date + timedelta(days=1)
    else:
        target_date = current_date

    await send_schedule(callback, callback.from_user.id, target_date, edit_mode=True)
    await callback.answer()


async def send_schedule(event: CallbackQuery | Message, platform_user_id: int, target_date: date,
                        edit_mode: bool = False):
    async with async_session() as session:
        user = await user_service.get_user_by_platform_id(session, "telegram", platform_user_id)

        # Проверка наличия пользователя и групп
        if not user or not user.groups:
            msg = "⚠️ Ошибка: ваш профиль не настроен. Пройдите регистрацию через /start"
            if isinstance(event, CallbackQuery):
                await event.message.answer(msg)
            else:
                await event.answer(msg)
            return

        # Берём первую (и единственную) группу
        group = user.groups[0]
        group_name = group.name
        group_id = group.id

        # Получаем занятия с подгрузкой связанных данных
        lessons = await schedule_service.get_lessons_for_student(session, group_id, target_date)
        has_next = await schedule_service.has_lessons_future(session, target_date, group_id=group_id)

        reply_markup = kb.get_schedule_keyboard(target_date, has_next)
        date_str = target_date.strftime("%d.%m.%Y")

        # Отправка в графическом формате
        if user.schedule_message_type == "pic":  # в БД хранится 'pic' для картинки
            image_bytes = await generate_schedule_image(lessons, target_date, group_name)
            input_file = BufferedInputFile(image_bytes, filename=f"schedule_{date_str}.png")
            caption = f"🖼️ Расписание на {date_str} для группы *{group_name}*"

            if edit_mode and isinstance(event, CallbackQuery):
                try:
                    await event.message.delete()
                except TelegramBadRequest:
                    pass
                await event.message.answer_photo(photo=input_file, caption=caption, reply_markup=reply_markup,
                                                 parse_mode="Markdown")
            else:
                target = event.message if isinstance(event, CallbackQuery) else event
                await target.answer_photo(photo=input_file, caption=caption, reply_markup=reply_markup,
                                          parse_mode="Markdown")

        # Текстовый формат
        else:
            text = f"📅 *Расписание на {date_str}* | Группа: *{group_name}*\n\n"
            if not lessons:
                text += "💤 В этот день занятий нет. Отдыхайте!"
            else:
                for idx, lesson in enumerate(lessons, 1):
                    time_start = lesson.start_datetime.strftime("%H:%M")
                    teacher = lesson.teacher.name if lesson.teacher else "Не указан"
                    text += f"{idx}. *{time_start}* — {lesson.subject.name}\n"
                    text += f"   🏫 Ауд: {lesson.classroom.name} | 👤 {teacher} ({lesson.type})\n"
                    if lesson.comment:
                        text += f"   📝 _Заметка: {lesson.comment}_\n"
                    text += "\n"

            if edit_mode and isinstance(event, CallbackQuery):
                try:
                    await event.message.edit_text(text, parse_mode="Markdown", reply_markup=reply_markup)
                except TelegramBadRequest:
                    await event.answer("🔄 Данные актуальны")
            else:
                target = event.message if isinstance(event, CallbackQuery) else event
                await target.answer(text, parse_mode="Markdown", reply_markup=reply_markup)

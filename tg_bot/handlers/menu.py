from datetime import datetime, timedelta, date
from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, BufferedInputFile, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.orm import selectinload

from database.connection import async_session
from database.models import Teacher
from services import user_service, schedule_service
from services.user_service import determine_user_role
from tg_bot import keyboards as kb
from config import settings
from utils.timezone import get_now, YEKT_TZ
from utils.image_generator import generate_schedule_image

menu_router = Router()


@menu_router.message(Command("menu"))
async def show_main_menu(message: Message):
    is_admin = message.from_user.id in settings.TG_ADMINS
    if is_admin:
        builder = InlineKeyboardBuilder()
        builder.button(text="📅 Посмотреть расписание", callback_data="menu:schedule")
        builder.button(text="⚙️ Настройки профиля", callback_data="menu:settings")
        builder.button(text="✍️ Написать админам", callback_data="menu:feedback")
        builder.button(text="🛠️ Админ-панель", callback_data="menu:admin_panel")
        builder.adjust(1)
        await message.answer(
            "👋 Вы находитесь в главном меню системы расписания.\n"
            "Выберите интересующий вас раздел:",
            reply_markup=builder.as_markup()
        )
    else:
        await message.answer(
            "👋 Вы находитесь в главном меню системы расписания.\n"
            "Выберите интересующий вас раздел:",
            reply_markup=kb.get_inline_main_menu(is_admin)
        )


@menu_router.callback_query(F.data == "menu:back")
async def callback_back_to_menu(callback: CallbackQuery):
    is_admin = callback.from_user.id in settings.TG_ADMINS
    if is_admin:
        builder = InlineKeyboardBuilder()
        builder.button(text="📅 Посмотреть расписание", callback_data="menu:schedule")
        builder.button(text="⚙️ Настройки профиля", callback_data="menu:settings")
        builder.button(text="✍️ Написать админам", callback_data="menu:feedback")
        builder.button(text="🛠️ Админ-панель", callback_data="menu:admin_panel")
        builder.adjust(1)
        text = "👋 Вы находитесь в главном меню системы расписания.\nВыберите интересующий вас раздел:"
        await safe_edit_or_new(callback.message, text, builder.as_markup())
    else:
        text = "👋 Вы находитесь в главном меню системы расписания.\nВыберите интересующий вас раздел:"
        await safe_edit_or_new(callback.message, text, kb.get_inline_main_menu(is_admin))
    await callback.answer()


@menu_router.callback_query(F.data == "menu:schedule")
async def callback_choose_schedule_period(callback: CallbackQuery):
    await callback.message.edit_text(
        "📅 Выберите период для просмотра расписания:",
        reply_markup=kb.get_schedule_period_keyboard()
    )
    await callback.answer()


@menu_router.callback_query(F.data == "schedule:today")
async def callback_schedule_today(callback: CallbackQuery):
    today = get_now().date()
    await send_schedule(callback, callback.from_user.id, today, edit_mode=False)
    await callback.message.delete()
    await callback.answer()


@menu_router.callback_query(F.data == "schedule:tomorrow")
async def callback_schedule_tomorrow(callback: CallbackQuery):
    tomorrow = get_now().date() + timedelta(days=1)
    await send_schedule(callback, callback.from_user.id, tomorrow, edit_mode=False)
    await callback.message.delete()
    await callback.answer()


@menu_router.callback_query(F.data == "schedule:this_week")
async def callback_schedule_this_week(callback: CallbackQuery):
    today = get_now().date()
    start_of_week = today - timedelta(days=today.weekday())
    await show_week_keyboard(callback, start_of_week, week_type="this")


@menu_router.callback_query(F.data == "schedule:next_week")
async def callback_schedule_next_week(callback: CallbackQuery):
    today = get_now().date()
    start_of_next_week = today - timedelta(days=today.weekday()) + timedelta(days=7)
    await show_week_keyboard(callback, start_of_next_week, week_type="next")


async def show_week_keyboard(callback: CallbackQuery, start_date: date, week_type: str):
    days = []
    for i in range(7):
        d = start_date + timedelta(days=i)
        weekday_ru = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"][i]
        days.append((d, f"{weekday_ru} {d.strftime('%d.%m')}"))

    builder = InlineKeyboardBuilder()
    for d, label in days:
        builder.button(text=label, callback_data=f"week_day:{d.strftime('%Y-%m-%d')}:{week_type}")
    builder.adjust(1)

    nav_buttons = []
    if week_type == "this":
        nav_buttons.append(InlineKeyboardButton(text="Следующая неделя ➡️", callback_data="schedule:next_week"))
    else:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Эта неделя", callback_data="schedule:this_week"))
    nav_buttons.append(InlineKeyboardButton(text="🔙 Главное меню", callback_data="menu:back"))
    builder.row(*nav_buttons)

    await callback.message.edit_text(
        "📅 Выберите день недели:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@menu_router.callback_query(F.data.startswith("week_day:"))
async def callback_week_day_selected(callback: CallbackQuery):
    _, date_str, week_type = callback.data.split(":")
    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    await send_schedule(callback, callback.from_user.id, target_date, edit_mode=False, from_week_mode=True)
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


async def send_schedule(
    event: CallbackQuery | Message,
    platform_user_id: int,
    target_date: date,
    edit_mode: bool = False,
    from_week_mode: bool = False
):
    async with async_session() as session:
        user = await user_service.get_user_by_platform_id(session, "telegram", platform_user_id)
        if not user:
            msg = "⚠️ Ошибка: ваш профиль не найден. Пройдите регистрацию через /start"
            if isinstance(event, CallbackQuery):
                await event.message.answer(msg)
            else:
                await event.answer(msg)
            return

        role = await user_service.determine_user_role(user)

        # --- Ветвление для студента / преподавателя ---
        lessons = []
        entity_name = None
        has_next = False

        if role == "student":
            if not user.groups:
                msg = "⚠️ Вы не привязаны к группе. Исправьте в настройках."
                if isinstance(event, CallbackQuery):
                    await event.message.answer(msg)
                else:
                    await event.answer(msg)
                return
            group = user.groups[0]
            group_id = group.id
            group_name = group.name
            lessons = await schedule_service.get_lessons_for_student(session, group_id, target_date)
            entity_name = group_name
            has_next = await schedule_service.has_lessons_future(session, target_date, group_id=group_id)

        elif role == "teacher":
            if not user.teacher_profile_id:
                msg = "⚠️ Ваш профиль преподавателя не активирован. Обратитесь к администратору."
                if isinstance(event, CallbackQuery):
                    await event.message.answer(msg)
                else:
                    await event.answer(msg)
                return
            lessons = await schedule_service.get_lessons_for_teacher(session, user.teacher_profile_id, target_date)
            teacher = await session.get(Teacher, user.teacher_profile_id)
            entity_name = teacher.name if teacher else "Преподаватель"
            has_next = await schedule_service.has_lessons_future(session, target_date, teacher_id=user.teacher_profile_id)

        else:  # admin (показываем как студента, если есть группа, иначе ошибка)
            if user.groups:
                group = user.groups[0]
                group_id = group.id
                group_name = group.name
                lessons = await schedule_service.get_lessons_for_student(session, group_id, target_date)
                entity_name = group_name
                has_next = await schedule_service.has_lessons_future(session, target_date, group_id=group_id)
            else:
                msg = "⚠️ У вас нет группы или преподавательского профиля."
                if isinstance(event, CallbackQuery):
                    await event.message.answer(msg)
                else:
                    await event.answer(msg)
                return

        reply_markup = kb.get_schedule_keyboard(target_date, has_next, role=role)
        date_str = target_date.strftime("%d.%m.%Y")

        # Отправка в графическом формате
        if user.schedule_message_type == "pic":
            image_bytes = await generate_schedule_image(lessons, target_date, entity_name)
            input_file = BufferedInputFile(image_bytes, filename=f"schedule_{date_str}.png")
            caption = f"🖼️ Расписание на {date_str} для {entity_name}"

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
            text = f"📅 *Расписание на {date_str}* | {entity_name}\n\n"
            if not lessons:
                text += "💤 В этот день занятий нет. Отдыхайте!"
            else:
                for idx, lesson in enumerate(lessons, 1):
                    time_start = lesson.start_datetime.astimezone(YEKT_TZ).strftime("%H:%M")
                    teacher = lesson.teacher.name if lesson.teacher else "Не указан"
                    subject_name = lesson.subject.name if lesson.subject else "Без названия"
                    classroom_name = lesson.classroom.name if lesson.classroom else "—"
                    text += f"{idx}. *{time_start}* — {subject_name}\n"
                    text += f"   🏫 Ауд: {classroom_name} | 👤 {teacher} ({lesson.type})\n"
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
async def safe_edit_or_new(message, new_text: str, reply_markup, parse_mode="Markdown"):
    """
    Безопасно заменяет текущее сообщение на новое.
    Если текущее сообщение содержит текст – редактирует его.
    Если это фото/медиа – удаляет старое и отправляет новое текстовое.
    """
    try:
        # Пытаемся отредактировать текст
        await message.edit_text(new_text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as e:
        if "message can't be edited" in str(e) or "there is no text" in str(e):
            # Если редактирование невозможно – удаляем и отправляем заново
            await message.delete()
            await message.answer(new_text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            raise

"""
Telegram bot adapter using aiogram 3.x with FSM for registration.
All business logic is delegated to core.services.
"""

import asyncio
from datetime import date, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile

from core import get_user_by_platform_id, get_teacher_by_id
from core.config import settings
from core.database import AsyncSessionLocal
from core.services import (
    get_or_create_user, get_user_by_id, get_all_groups, set_student_group,
    request_teacher_role, update_notification_setting, update_schedule_message_type,
    get_schedule_text_cached, get_schedule_image_cached, get_user_role,
    get_group_by_user_id, add_comment_to_lesson, get_pending_teacher_requests,
    get_lessons_for_user, get_lesson_by_id, get_all_teachers, create_teacher,
    approve_teacher_request, reject_teacher_request
)
from core.models import Platform, ScheduleMessageType, LessonType
from core.utils import get_current_date

bot = Bot(token=settings.tg_bot_token)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ---------- FSM states for registration ----------
class RegState(StatesGroup):
    role = State()
    group = State()
    format = State()
    notification = State()

# ---------- FSM state for comment input ----------
class CommentState(StatesGroup):
    waiting_for_comment = State()
    selecting_lesson = State()

# ---------- FSM state for feedback ----------
class FeedbackState(StatesGroup):
    waiting_for_feedback = State()

# ---------- Main Menu Keyboards ----------

def get_main_menu_keyboard(role: str) -> InlineKeyboardMarkup:
    """Return main menu keyboard based on user role."""
    buttons = [
        [InlineKeyboardButton(text="📅 Расписание", callback_data="menu_schedule")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu_settings")],
        [InlineKeyboardButton(text="💬 Обратная связь", callback_data="menu_feedback")],
    ]
    if role == "teacher":
        buttons.insert(0, [InlineKeyboardButton(text="✏️ Комментировать занятия", callback_data="menu_comment")])
    elif role == "admin":
        buttons.insert(0, [InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_schedule_menu_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for schedule navigation."""
    today = get_current_date()
    tomorrow = today + timedelta(days=1)
    week_end = today + timedelta(days=6)
    next_week_start = today + timedelta(days=7)
    next_week_end = next_week_start + timedelta(days=6)
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📆 Сегодня", callback_data=f"schedule_{today.isoformat()}"),
            InlineKeyboardButton(text="➡️ Завтра", callback_data=f"schedule_{tomorrow.isoformat()}")
        ],
        [
            InlineKeyboardButton(text="📅 Текущая неделя", callback_data=f"schedule_week_{today.isoformat()}_{week_end.isoformat()}"),
            InlineKeyboardButton(text="⏩ Следующая неделя", callback_data=f"schedule_week_{next_week_start.isoformat()}_{next_week_end.isoformat()}")
        ],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")]
    ])

def get_lessons_for_comment_keyboard(lessons: list) -> InlineKeyboardMarkup:
    """Keyboard with lessons that teacher can comment on (today's lessons)."""
    buttons = []
    for lesson in lessons:
        subject_name = lesson.subject.name if lesson.subject else "—"
        start_time = lesson.start_datetime.astimezone().strftime("%H:%M")
        buttons.append([InlineKeyboardButton(
            text=f"{start_time} | {subject_name}",
            callback_data=f"comment_lesson_{lesson.id}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_feedback_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for feedback options."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Сообщение администратору", callback_data="feedback_admin")],
        [InlineKeyboardButton(text="🐛 Сообщить об ошибке", callback_data="feedback_bug")],
        [InlineKeyboardButton(text="💡 Предложение", callback_data="feedback_suggestion")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")]
    ])

# ---------- Role selection keyboard (registration) ----------
def role_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍🎓 Студент", callback_data="role_student")],
        [InlineKeyboardButton(text="👨‍🏫 Преподаватель", callback_data="role_teacher")]
    ])

def group_keyboard(groups):
    buttons = []
    for g in groups:
        buttons.append([InlineKeyboardButton(text=g.name, callback_data=f"group_{g.id}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_role")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def format_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼 Картинкой", callback_data="format_pic")],
        [InlineKeyboardButton(text="📝 Текстом", callback_data="format_text")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_group")]
    ])

def notification_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да", callback_data="notif_on")],
        [InlineKeyboardButton(text="❌ Нет", callback_data="notif_off")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_format")]
    ])

# ---------- Helper function to check if user is registered ----------
async def is_user_registered(user_id: int) -> tuple[bool, str | None]:
    async with AsyncSessionLocal() as db:
        user = await get_user_by_platform_id(db, Platform.TELEGRAM, user_id)
        if not user:
            return False, None

        # 1. Администратор (важнее всего)
        if user.is_admin:
            return True, "admin"

        # 2. Преподаватель
        if user.teacher_profile_id is not None:
            return True, "teacher"

        # 3. Студент (есть хотя бы одна группа)
        from core.models import GroupUser
        from sqlalchemy import select
        result = await db.execute(
            select(GroupUser).where(GroupUser.user_id == user.id).limit(1)
        )
        if result.first() is not None:
            return True, "student"

    return False, None

# ---------- Command /start ----------
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    async with AsyncSessionLocal() as db:
        user = await get_or_create_user(db, Platform.TELEGRAM, message.from_user.id, message.from_user.full_name)

        # 🚀 АБСОЛЮТНЫЙ ПРИОРИТЕТ: если админ -> сразу полное меню
        if user.is_admin:
            await message.answer(
                get_welcome_text(user.name, "admin"),
                reply_markup=get_main_menu_keyboard("admin")
            )
            return

        # Для обычных пользователей: проверяем, зарегистрированы ли они
        from core.models import GroupUser
        from sqlalchemy import select
        result = await db.execute(select(GroupUser).where(GroupUser.user_id == user.id).limit(1))
        has_group = result.first() is not None

        if user.teacher_profile_id is not None or has_group:
            role = get_user_role(user)
            await message.answer(get_welcome_text(user.name, role), reply_markup=get_main_menu_keyboard(role))
            return

    # Новая регистрация только для НЕ-админов
    await message.answer("🎓 Добро пожаловать в бот расписания!\n\nКто вы?", reply_markup=role_keyboard())
    await state.set_state(RegState.role)


def get_welcome_text(name: str, role: str) -> str:
    """Generate welcome message based on role."""
    if role == "student":
        return f"👋 Здравствуйте, {name}!\n\nВы зарегистрированы как **студент**.\n\nИспользуйте меню для просмотра расписания и настроек."
    elif role == "teacher":
        return f"👋 Здравствуйте, {name}!\n\nВы зарегистрированы как **преподаватель**.\n\nВы можете:\n• Просматривать расписание\n• Добавлять комментарии к своим занятиям\n• Настраивать уведомления"
    elif role == "admin":
        return f"👋 Здравствуйте, {name}!\n\nВы зарегистрированы как **администратор**.\n\nВам доступны все функции бота, включая админ-панель."
    return f"👋 Здравствуйте, {name}!"

# ---------- Role selection (registration) ----------
@dp.callback_query(StateFilter(RegState.role), F.data.startswith("role_"))
async def process_role(callback: types.CallbackQuery, state: FSMContext):
    role = callback.data.split("_")[1]
    await state.update_data(role=role)
    if role == "student":
        async with AsyncSessionLocal() as db:
            groups = await get_all_groups(db)
        if not groups:
            await callback.message.edit_text("❌ Группы не найдены. Обратитесь к администратору.")
            return
        await callback.message.edit_text("Выберите вашу группу:", reply_markup=group_keyboard(groups))
        await state.set_state(RegState.group)
    else:  # teacher
        async with AsyncSessionLocal() as db:
            await request_teacher_role(db, callback.from_user.id)
        await callback.message.edit_text(
            "👨‍🏫 Вы выбрали роль преподавателя.\n\n"
            "Для доступа к функциям преподавателя необходимо подтверждение администратора. "
            "Администратор будет уведомлён. Пожалуйста, ожидайте.\n\n"
            "Вы можете продолжать пользоваться ботом как студент, но для этого зарегистрируйтесь заново с командой /start и выберите 'Студент'."
        )
        await state.clear()
    await callback.answer()

# ---------- Group selection (registration) ----------
@dp.callback_query(StateFilter(RegState.group), F.data.startswith("group_"))
async def process_group(callback: types.CallbackQuery, state: FSMContext):
    group_id = int(callback.data.split("_")[1])
    await state.update_data(group_id=group_id)
    await callback.message.edit_text("В каком формате вы хотите получать расписание?", reply_markup=format_keyboard())
    await state.set_state(RegState.format)
    await callback.answer()

@dp.callback_query(StateFilter(RegState.group), F.data == "back_role")
async def back_to_role(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Кто вы?", reply_markup=role_keyboard())
    await state.set_state(RegState.role)
    await callback.answer()

# ---------- Format selection (registration) ----------
@dp.callback_query(StateFilter(RegState.format), F.data.startswith("format_"))
async def process_format(callback: types.CallbackQuery, state: FSMContext):
    fmt = callback.data.split("_")[1]
    msg_type = ScheduleMessageType.PICTURE if fmt == "pic" else ScheduleMessageType.TEXT
    await state.update_data(message_type=msg_type)
    await callback.message.edit_text("Хотите получать ежедневные уведомления о расписании на завтра?", reply_markup=notification_keyboard())
    await state.set_state(RegState.notification)
    await callback.answer()

@dp.callback_query(StateFilter(RegState.format), F.data == "back_group")
async def back_to_group(callback: types.CallbackQuery, state: FSMContext):
    async with AsyncSessionLocal() as db:
        groups = await get_all_groups(db)
    await callback.message.edit_text("Выберите вашу группу:", reply_markup=group_keyboard(groups))
    await state.set_state(RegState.group)
    await callback.answer()

# ---------- Notification selection and final save (registration) ----------
@dp.callback_query(StateFilter(RegState.notification), F.data.startswith("notif_"))
async def process_notification(callback: types.CallbackQuery, state: FSMContext):
    notif = callback.data.split("_")[1]
    notif_enabled = (notif == "on")
    data = await state.get_data()
    group_id = data.get("group_id")
    msg_type = data.get("message_type")

    async with AsyncSessionLocal() as db:
        user = await get_user_by_platform_id(db, Platform.TELEGRAM, callback.from_user.id)
        if user:
            await set_student_group(db, user.id, group_id)
            await update_notification_setting(db, user.id, notif_enabled)
            await update_schedule_message_type(db, user.id, msg_type)

            await callback.message.edit_text(
                "✅ Регистрация завершена!\n\nТеперь вы можете пользоваться ботом через меню.")

            # После регистрации проверяем, не стал ли пользователь админом
            role = get_user_role(user)
            await callback.message.answer(
                get_welcome_text(user.name, role),
                reply_markup=get_main_menu_keyboard(role)
            )
            await state.clear()
            await callback.answer()

    # Show main menu after registration
    async with AsyncSessionLocal() as db:
        user = await get_user_by_platform_id(db, Platform.TELEGRAM, callback.from_user.id)
        role = get_user_role(user)
        await callback.message.answer(
            get_welcome_text(user.name, role),
            reply_markup=get_main_menu_keyboard(role)
        )
    await state.clear()
    await callback.answer()

@dp.callback_query(StateFilter(RegState.notification), F.data == "back_format")
async def back_to_format(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("В каком формате вы хотите получать расписание?", reply_markup=format_keyboard())
    await state.set_state(RegState.format)
    await callback.answer()

# ---------- Main Menu Navigation ----------
@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    async with AsyncSessionLocal() as db:
        user = await get_user_by_platform_id(db, Platform.TELEGRAM, callback.from_user.id)
        if user:
            role = get_user_role(user)
            await callback.message.edit_text(
                get_welcome_text(user.name, role),
                reply_markup=get_main_menu_keyboard(role)
            )
        else:
            await callback.message.edit_text("Главное меню", reply_markup=get_main_menu_keyboard("student"))
    await callback.answer()

# ---------- Menu: Schedule ----------
@dp.callback_query(F.data == "menu_schedule")
async def menu_schedule(callback: types.CallbackQuery):
    is_registered, _ = await is_user_registered(callback.from_user.id)
    if not is_registered:
        await callback.message.answer("Сначала зарегистрируйтесь: /start")
        await callback.answer()
        return
    await callback.message.edit_text("📅 Выберите период:", reply_markup=get_schedule_menu_keyboard())
    await callback.answer()

# ---------- Schedule Callbacks ----------
@dp.callback_query(F.data.startswith("schedule_"))
async def process_schedule_callback(callback: types.CallbackQuery):
    data = callback.data
    user_id = callback.from_user.id


    is_registered, _ = await is_user_registered(user_id)
    if not is_registered:
        await callback.message.answer("Сначала зарегистрируйтесь: /start")
        await callback.answer()
        return

    if data.startswith("schedule_week_"):
        # format: schedule_week_start_end
        parts = data.split("_")
        start_str = parts[2]
        end_str = parts[3]
        start_date = date.fromisoformat(start_str)
        end_date = date.fromisoformat(end_str)
        # Показываем расписание на каждый день недели
        text_parts = []
        delta = timedelta(days=1)
        cur = start_date
        while cur <= end_date:
            async with AsyncSessionLocal() as db:
                user = await get_user_by_platform_id(db, Platform.TELEGRAM, callback.from_user.id)
            day_text = await get_schedule_text_cached(user.id, cur)
            text_parts.append(day_text)
            cur += delta
        full_text = "\n\n".join(text_parts)
        await callback.message.edit_text(full_text, parse_mode="Markdown")
        # Add return button
        await callback.message.answer("🔙 Вернуться в меню", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")]
        ]))
    else:
        # single day: schedule_YYYY-MM-DD
        date_str = data.split("_")[1]
        target_date = date.fromisoformat(date_str)
        async with AsyncSessionLocal() as db:
            user =  await get_user_by_platform_id(db, Platform.TELEGRAM, callback.from_user.id)
            msg_type = user.schedule_message_type if user else ScheduleMessageType.TEXT
            role = get_user_role(user) if user else "student"

            if msg_type == ScheduleMessageType.PICTURE and role == "student":
                try:
                    img_bytes = await get_schedule_image_cached(user.id, target_date)
                    if img_bytes:
                        await callback.message.answer_photo(
                            BufferedInputFile(img_bytes, filename="schedule.png"),
                            caption=f"Расписание на {target_date.strftime('%d.%m.%Y')}"
                        )
                        await callback.message.answer("🔙 Вернуться в меню", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")]
                        ]))
                    else:
                        await callback.message.edit_text("Не удалось сгенерировать картинку.")
                except Exception as e:
                    await callback.message.edit_text(f"❌ Ошибка: {e}")
            else:
                text = await get_schedule_text_cached(user.id, target_date)
                await callback.message.edit_text(text, parse_mode="Markdown")
                await callback.message.answer("🔙 Вернуться в меню", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")]
                ]))
    await callback.answer()

# ---------- Menu: Settings ----------
@dp.callback_query(F.data == "menu_settings")
async def menu_settings(callback: types.CallbackQuery):
    is_registered, _ = await is_user_registered(callback.from_user.id)
    if not is_registered:
        await callback.message.answer("Сначала зарегистрируйтесь: /start")
        await callback.answer()
        return

    async with AsyncSessionLocal() as db:
        user = await get_user_by_platform_id(db, Platform.TELEGRAM, callback.from_user.id)
        if not user:
            await callback.message.answer("Сначала зарегистрируйтесь: /start")
            await callback.answer()
            return
        role = get_user_role(user)
        settings_text = (
            f"⚙️ **Настройки**\n\n"
            f"👤 Роль: {role}\n"
            f"🔔 Уведомления: {'✅ вкл' if user.is_notification_on else '❌ выкл'}\n"
            f"🖼 Формат расписания: {'🖼 картинка' if user.schedule_message_type == ScheduleMessageType.PICTURE else '📝 текст'}\n\n"
            f"Используйте кнопки ниже для изменения настроек:"
        )
        settings_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔔 Вкл уведомления", callback_data="toggle_notif_on"),
             InlineKeyboardButton(text="🔕 Выкл уведомления", callback_data="toggle_notif_off")],
            [InlineKeyboardButton(text="🖼 Формат: картинка", callback_data="toggle_format_pic"),
             InlineKeyboardButton(text="📝 Формат: текст", callback_data="toggle_format_text")],
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")]
        ])
        await callback.message.edit_text(settings_text, parse_mode="Markdown", reply_markup=settings_keyboard)
    await callback.answer()

@dp.callback_query(F.data.startswith("toggle_notif_"))
async def toggle_notification(callback: types.CallbackQuery):
    enabled = callback.data == "toggle_notif_on"
    async with AsyncSessionLocal() as db:
        user = await get_user_by_platform_id(db, Platform.TELEGRAM, callback.from_user.id)
        if user:
            await update_notification_setting(db, user.id, enabled)
    await callback.answer(f"Уведомления {'включены' if enabled else 'выключены'}")
    # Refresh settings menu
    await menu_settings(callback)

@dp.callback_query(F.data.startswith("toggle_format_"))
async def toggle_format(callback: types.CallbackQuery):
    format_type = callback.data.split("_")[2]  # pic or text
    msg_type = ScheduleMessageType.PICTURE if format_type == "pic" else ScheduleMessageType.TEXT
    async with AsyncSessionLocal() as db:
        user = await get_user_by_platform_id(db, Platform.TELEGRAM, callback.from_user.id)
        if user:
            await update_schedule_message_type(db, user.id, msg_type)
    await callback.answer(f"Формат расписания: {'картинка' if format_type == 'pic' else 'текст'}")
    # Refresh settings menu
    await menu_settings(callback)

# ---------- Menu: Feedback ----------
@dp.callback_query(F.data == "menu_feedback")
async def menu_feedback(callback: types.CallbackQuery):
    feedback_text = (
        "💬 **Обратная связь**\n\n"
        "Выберите тип вашего обращения:"
    )
    await callback.message.edit_text(feedback_text, parse_mode="Markdown", reply_markup=get_feedback_keyboard())
    await callback.answer()

@dp.callback_query(F.data.startswith("feedback_"))
async def process_feedback_type(callback: types.CallbackQuery, state: FSMContext):
    feedback_type = callback.data.split("_")[1]
    type_names = {
        "admin": "Сообщение администратору",
        "bug": "Сообщение об ошибке",
        "suggestion": "Предложение"
    }
    await state.update_data(feedback_type=feedback_type, feedback_type_name=type_names.get(feedback_type, "Обращение"))
    await callback.message.edit_text(
        f"📝 Напишите текст вашего обращения (тип: {type_names.get(feedback_type, 'Обращение')}):\n\n"
        f"Отправьте текстовое сообщение. Для отмены отправьте /cancel"
    )
    await state.set_state(FeedbackState.waiting_for_feedback)
    await callback.answer()

@dp.message(StateFilter(FeedbackState.waiting_for_feedback))
async def receive_feedback(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        is_registered, role = await is_user_registered(message.from_user.id)
        await message.answer("❌ Отправка отменена.", reply_markup=get_main_menu_keyboard(role or "student"))
        return

    data = await state.get_data()
    feedback_type = data.get("feedback_type", "unknown")
    feedback_type_name = data.get("feedback_type_name", "Обращение")

    await message.answer(
        f"✅ Ваше обращение принято!\n\n"
        f"Тип: {feedback_type_name}\n"
        f"Текст: {message.text[:200]}...\n\n"
        f"Спасибо за обратную связь!"
    )

    # Notify admins
    for admin_id in settings.admin_tg_ids:
        try:
            await bot.send_message(
                admin_id,
                f"📨 Новое обращение!\n"
                f"От: {message.from_user.full_name} (ID: {message.from_user.id})\n"
                f"Тип: {feedback_type_name}\n"
                f"Текст: {message.text}"
            )
        except:
            pass

    await state.clear()
    is_registered, role = await is_user_registered(message.from_user.id)
    await message.answer("🔙 Главное меню:", reply_markup=get_main_menu_keyboard(role or "student"))

# ---------- Menu: Comment for Teachers ----------
@dp.callback_query(F.data == "menu_comment")
async def menu_comment(callback: types.CallbackQuery, state: FSMContext):
    async with AsyncSessionLocal() as db:
        user = await get_user_by_platform_id(db, Platform.TELEGRAM, callback.from_user.id)
        if not user or user.teacher_profile_id is None:
            await callback.answer("Только преподаватели могут комментировать занятия", show_alert=True)
            return

        # Get today's lessons for this teacher
        today = get_current_date()
        lessons = await get_lessons_for_user(db, user.id, today, today)

        if not lessons:
            await callback.message.edit_text(
                "📭 На сегодня у вас нет занятий для комментирования.\n\n"
                "Комментарии можно добавлять только к занятиям, которые уже прошли или запланированы на сегодня.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")]
                ])
            )
            await callback.answer()
            return

        await callback.message.edit_text(
            "✏️ **Выберите занятие для добавления комментария:**\n\n"
            f"Сегодня, {today.strftime('%d.%m.%Y')}",
            parse_mode="Markdown",
            reply_markup=get_lessons_for_comment_keyboard(lessons)
        )
        await state.set_state(CommentState.selecting_lesson)
    await callback.answer()

@dp.callback_query(StateFilter(CommentState.selecting_lesson), F.data.startswith("comment_lesson_"))
async def select_lesson_for_comment(callback: types.CallbackQuery, state: FSMContext):
    lesson_id = int(callback.data.split("_")[2])
    await state.update_data(comment_lesson_id=lesson_id)

    # Get lesson details
    async with AsyncSessionLocal() as db:
        lesson = await get_lesson_by_id(db, lesson_id)
        if lesson:
            subject_name = lesson.subject.name if lesson.subject else "—"
            start_time = lesson.start_datetime.astimezone().strftime("%H:%M")
            lesson_info = f"{start_time} | {subject_name}"
            if lesson.comment:
                lesson_info += f"\n\nТекущий комментарий: {lesson.comment}"
        else:
            lesson_info = "Занятие"

    await callback.message.edit_text(
        f"✏️ **Добавление комментария**\n\n"
        f"Занятие: {lesson_info}\n\n"
        f"Введите текст комментария (до 500 символов):\n"
        f"Для отмены отправьте /cancel",
        parse_mode="Markdown"
    )
    await state.set_state(CommentState.waiting_for_comment)
    await callback.answer()

@dp.message(StateFilter(CommentState.waiting_for_comment))
async def process_comment_text(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        is_registered, role = await is_user_registered(message.from_user.id)
        await message.answer("❌ Добавление комментария отменено.", reply_markup=get_main_menu_keyboard(role or "teacher"))
        return

    if len(message.text) > 500:
        await message.answer("❌ Комментарий слишком длинный (максимум 500 символов). Попробуйте снова или отправьте /cancel")
        return

    data = await state.get_data()
    lesson_id = data.get("comment_lesson_id")

    async with AsyncSessionLocal() as db:
        success, msg = await add_comment_to_lesson(db, lesson_id, message.from_user.id, message.text)

    await message.answer(f"{'✅' if success else '❌'} {msg}")

    await state.clear()
    is_registered, role = await is_user_registered(message.from_user.id)
    await message.answer("🔙 Главное меню:", reply_markup=get_main_menu_keyboard(role or "teacher"))

# ---------- Admin Panel ----------
@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: types.CallbackQuery):
    async with AsyncSessionLocal() as db:
        user = await get_user_by_platform_id(db, Platform.TELEGRAM, callback.from_user.id)
        if not user or not user.is_admin:
            await callback.answer("⛔ У вас нет прав администратора", show_alert=True)
            return

    admin_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Управление пользователями", callback_data="admin_users")],
        [InlineKeyboardButton(text="📚 Управление расписанием", callback_data="admin_schedule")],
        [InlineKeyboardButton(text="🏫 Управление группами", callback_data="admin_groups")],
        [InlineKeyboardButton(text="👨‍🏫 Заявки преподавателей", callback_data="admin_teacher_requests")],
        [InlineKeyboardButton(text="📊 Логи", callback_data="admin_logs")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")]
    ])

    await callback.message.edit_text(
        "👑 **Админ-панель**\n\n"
        "Выберите раздел для управления:",
        parse_mode="Markdown",
        reply_markup=admin_keyboard
    )
    await callback.answer()

# Placeholder handlers for admin sub-menus
@dp.callback_query(F.data == "admin_users")
async def admin_users(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "👥 Управление пользователями\n\n🚧 В разработке\n\nФункционал будет доступен в следующей версии.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад в админ-панель", callback_data="admin_panel")],
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_schedule")
async def admin_schedule(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "📚 Управление расписанием\n\n🚧 В разработке\n\nФункционал будет доступен в следующей версии.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад в админ-панель", callback_data="admin_panel")],
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_groups")
async def admin_groups(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🏫 Управление группами\n\n🚧 В разработке\n\nФункционал будет доступен в следующей версии.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад в админ-панель", callback_data="admin_panel")],
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_teacher_requests")
async def admin_teacher_requests(callback: types.CallbackQuery):
    async with AsyncSessionLocal() as db:
        users = await get_pending_teacher_requests(db)
        if not users:
            await callback.message.edit_text(
                "📋 Заявки преподавателей\n\n✅ Нет активных заявок.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Назад в админ-панель", callback_data="admin_panel")],
                    [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")]
                ])
            )
            await callback.answer()
            return

        text = "📋 **Заявки на роль преподавателя:**\n\n"
        buttons = []
        for u in users:
            text += f"• {u.name} (ID: {u.id})\n"
            buttons.append([InlineKeyboardButton(text=f"✅ Одобрить {u.name}", callback_data=f"approve_teacher_{u.id}")])
            buttons.append([InlineKeyboardButton(text=f"❌ Отклонить {u.name}", callback_data=f"reject_teacher_{u.id}")])
        buttons.append([InlineKeyboardButton(text="🔙 Назад в админ-панель", callback_data="admin_panel")])
        buttons.append([InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")])

        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(F.data.startswith("approve_teacher_"))
async def approve_teacher(callback: types.CallbackQuery):
    target_id = int(callback.data.split("_")[2])
    async with AsyncSessionLocal() as db:
        admin_user = await get_user_by_platform_id(db, Platform.TELEGRAM, callback.from_user.id)
        teachers = await get_all_teachers(db)
        if teachers:
            teacher_id = teachers[0].id
        else:
            teacher = await create_teacher(db, admin_user.id, "Новый преподаватель")
            teacher_id = teacher.id if teacher else 1

        success = await approve_teacher_request(db, admin_user.id, target_id, teacher_id)
        await callback.answer(f"{'✅' if success else '❌'} Заявка обработана")
    await admin_teacher_requests(callback)

@dp.callback_query(F.data.startswith("reject_teacher_"))
async def reject_teacher(callback: types.CallbackQuery):
    target_id = int(callback.data.split("_")[2])
    async with AsyncSessionLocal() as db:
        admin_user = await get_user_by_platform_id(db, Platform.TELEGRAM, callback.from_user.id)
        success = await reject_teacher_request(db, admin_user.id, target_id)
        await callback.answer(f"{'✅' if success else '❌'} Заявка отклонена")
    await admin_teacher_requests(callback)

@dp.callback_query(F.data == "admin_logs")
async def admin_logs(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "📊 Логи системы\n\n🚧 В разработке\n\nФункционал будет доступен в следующей версии.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад в админ-панель", callback_data="admin_panel")],
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")]
        ])
    )
    await callback.answer()

# ---------- Legacy command handlers (for compatibility) ----------
@dp.message(Command("schedule"))
async def cmd_schedule(message: types.Message):
    is_registered, _ = await is_user_registered(message.from_user.id)
    if not is_registered:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return
    await message.answer("📅 Выберите период:", reply_markup=get_schedule_menu_keyboard())

@dp.message(Command("tomorrow"))
async def cmd_tomorrow(message: types.Message):
    is_registered, _ = await is_user_registered(message.from_user.id)
    if not is_registered:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return
    tomorrow = get_current_date() + timedelta(days=1)
    text = await get_schedule_text_cached(message.from_user.id, tomorrow)
    await message.answer(text, parse_mode="Markdown")

@dp.message(Command("week"))
async def cmd_week(message: types.Message):
    is_registered, _ = await is_user_registered(message.from_user.id)
    if not is_registered:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return
    today = get_current_date()
    text_parts = []
    for i in range(7):
        target = today + timedelta(days=i)
        async with AsyncSessionLocal() as db:
            user = get_user_by_platform_id(db, Platform.TELEGRAM, message.from_user.id)
        day_text = await get_schedule_text_cached(user.id, target)
        text_parts.append(day_text)
    full_text = "\n\n".join(text_parts)
    await message.answer(full_text, parse_mode="Markdown")

@dp.message(Command("settings"))
async def cmd_settings(message: types.Message):
    is_registered, _ = await is_user_registered(message.from_user.id)
    if not is_registered:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return

    async with AsyncSessionLocal() as db:
        user = await get_user_by_platform_id(db, Platform.TELEGRAM, message.from_user.id)
        if not user:
            await message.answer("Сначала зарегистрируйтесь: /start")
            return
        role = get_user_role(user)
        settings_text = (
            f"⚙️ **Настройки**\n\n"
            f"👤 Роль: {role}\n"
            f"🔔 Уведомления: {'✅ вкл' if user.is_notification_on else '❌ выкл'}\n"
            f"🖼 Формат расписания: {'🖼 картинка' if user.schedule_message_type == ScheduleMessageType.PICTURE else '📝 текст'}\n\n"
        )
        await message.answer(settings_text, parse_mode="Markdown")

@dp.message(Command("notify_on"))
async def cmd_notify_on(message: types.Message):
    async with AsyncSessionLocal() as db:
        user = await get_user_by_platform_id(db, Platform.TELEGRAM, message.from_user.id)
        if user:
            await update_notification_setting(db, user.id, True)
            await message.answer("✅ Уведомления включены.")
        else:
            await message.answer("Сначала зарегистрируйтесь: /start")

@dp.message(Command("notify_off"))
async def cmd_notify_off(message: types.Message):
    async with AsyncSessionLocal() as db:
        user = await get_user_by_platform_id(db, Platform.TELEGRAM, message.from_user.id)
        if user:
            await update_notification_setting(db, user.id, False)
            await message.answer("🔕 Уведомления выключены.")
        else:
            await message.answer("Сначала зарегистрируйтесь: /start")

@dp.message(Command("format_pic"))
async def cmd_format_pic(message: types.Message):
    async with AsyncSessionLocal() as db:
        user = await get_user_by_platform_id(db, Platform.TELEGRAM, message.from_user.id)
        if user:
            await update_schedule_message_type(db, user.id, ScheduleMessageType.PICTURE)
            await message.answer("🖼 Формат расписания: картинка")
        else:
            await message.answer("Сначала зарегистрируйтесь: /start")

@dp.message(Command("format_text"))
async def cmd_format_text(message: types.Message):
    async with AsyncSessionLocal() as db:
        user = await get_user_by_platform_id(db, Platform.TELEGRAM, message.from_user.id)
        if user:
            await update_schedule_message_type(db, user.id, ScheduleMessageType.TEXT)
            await message.answer("📝 Формат расписания: текст")
        else:
            await message.answer("Сначала зарегистрируйтесь: /start")

@dp.message(Command("comment"))
async def cmd_comment(message: types.Message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Использование: /comment <id урока> <комментарий>")
        return
    try:
        lesson_id = int(parts[1])
        comment_text = parts[2]
    except ValueError:
        await message.answer("ID урока должен быть числом.")
        return
    async with AsyncSessionLocal() as db:
        success, msg = await add_comment_to_lesson(db, lesson_id, message.from_user.id, comment_text)
    await message.answer(msg)

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id not in settings.admin_tg_ids:
        await message.answer("⛔ У вас нет прав администратора.")
        return
    async with AsyncSessionLocal() as db:
        users = await get_pending_teacher_requests(db)
        if not users:
            await message.answer("Нет заявок от преподавателей.")
            return
        text = "📋 Заявки на роль преподавателя:\n\n"
        for u in users:
            text += f"ID: {u.id} | Имя: {u.name} | TG ID: {u.tg_id}\n"
        await message.answer(text)

@dp.message(Command("menu"))
async def cmd_menu(message: types.Message):
    is_registered, role = await is_user_registered(message.from_user.id)
    if not is_registered:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return

    async with AsyncSessionLocal() as db:
        user = await get_user_by_platform_id(db, Platform.TELEGRAM, message.from_user.id)
        if user:
            await message.answer(get_welcome_text(user.name, role or "student"), reply_markup=get_main_menu_keyboard(role or "student"))
        else:
            await message.answer("Сначала зарегистрируйтесь: /start")

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    text = (
        "📚 **Помощь**\n\n"
        "/start - начать регистрацию или открыть меню\n"
        "/menu - главное меню\n"
        "/schedule - расписание\n"
        "/tomorrow - расписание на завтра\n"
        "/week - расписание на неделю\n"
        "/settings - настройки\n"
        "/notify_on - включить уведомления\n"
        "/notify_off - выключить\n"
        "/format_pic - картинкой\n"
        "/format_text - текстом\n"
        "/comment <id> <текст> - добавить комментарий к занятию (преподаватели)\n"
        "/help - это сообщение"
    )
    await message.answer(text, parse_mode="Markdown")

# ---------- Cancel command for FSM ----------
@dp.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нет активных действий для отмены.")
        return
    await state.clear()
    is_registered, role = await is_user_registered(message.from_user.id)
    await message.answer("❌ Действие отменено.", reply_markup=get_main_menu_keyboard(role or "student"))

# ---------- Run bot ----------
async def start_telegram_bot():
    await dp.start_polling(bot, skip_updates=True)
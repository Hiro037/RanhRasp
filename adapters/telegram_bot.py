"""
Telegram bot adapter using aiogram 3.x with FSM for registration.
All business logic is delegated to core.services.
"""

import asyncio
from datetime import date, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile

from core import get_user_by_platform_id
from core.config import settings
from core.database import AsyncSessionLocal
from core.services import (
    get_or_create_user, get_user_by_id, get_all_groups, set_student_group,
    request_teacher_role, update_notification_setting, update_schedule_message_type,
    get_schedule_text_cached, get_schedule_image_cached, get_user_role,
    get_group_by_user_id, add_comment_to_lesson, get_pending_teacher_requests
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

# ---------- Keyboards ----------
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

def schedule_nav_keyboard():
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
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")
        ]
    ])

# ---------- Command /start ----------
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    async with AsyncSessionLocal() as db:
        user = await get_or_create_user(db, Platform.TELEGRAM, message.from_user.id, message.from_user.full_name)
        # Если уже зарегистрирован (есть группа или teacher_profile)
        if user.teacher_profile_id is not None or user.groups:
            await message.answer(
                "✅ Вы уже зарегистрированы.\n\n"
                "Доступные команды:\n"
                "/schedule - расписание\n"
                "/tomorrow - расписание на завтра\n"
                "/week - расписание на неделю\n"
                "/settings - настройки\n"
                "/help - помощь"
            )
            return
    # Новая регистрация
    await message.answer("🎓 Добро пожаловать в бот расписания!\n\nКто вы?", reply_markup=role_keyboard())
    await state.set_state(RegState.role)

# ---------- Role selection ----------
@dp.callback_query(RegState.role, F.data.startswith("role_"))
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

# ---------- Group selection ----------
@dp.callback_query(RegState.group, F.data.startswith("group_"))
async def process_group(callback: types.CallbackQuery, state: FSMContext):
    group_id = int(callback.data.split("_")[1])
    await state.update_data(group_id=group_id)
    await callback.message.edit_text("В каком формате вы хотите получать расписание?", reply_markup=format_keyboard())
    await state.set_state(RegState.format)
    await callback.answer()

@dp.callback_query(RegState.group, F.data == "back_role")
async def back_to_role(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Кто вы?", reply_markup=role_keyboard())
    await state.set_state(RegState.role)
    await callback.answer()

# ---------- Format selection ----------
@dp.callback_query(RegState.format, F.data.startswith("format_"))
async def process_format(callback: types.CallbackQuery, state: FSMContext):
    fmt = callback.data.split("_")[1]
    msg_type = ScheduleMessageType.PICTURE if fmt == "pic" else ScheduleMessageType.TEXT
    await state.update_data(message_type=msg_type)
    await callback.message.edit_text("Хотите получать ежедневные уведомления о расписании на завтра?", reply_markup=notification_keyboard())
    await state.set_state(RegState.notification)
    await callback.answer()

@dp.callback_query(RegState.format, F.data == "back_group")
async def back_to_group(callback: types.CallbackQuery, state: FSMContext):
    async with AsyncSessionLocal() as db:
        groups = await get_all_groups(db)
    await callback.message.edit_text("Выберите вашу группу:", reply_markup=group_keyboard(groups))
    await state.set_state(RegState.group)
    await callback.answer()

# ---------- Notification selection and final save ----------
@dp.callback_query(RegState.notification, F.data.startswith("notif_"))
async def process_notification(callback: types.CallbackQuery, state: FSMContext):
    notif = callback.data.split("_")[1]
    notif_enabled = (notif == "on")
    data = await state.get_data()
    group_id = data.get("group_id")
    msg_type = data.get("message_type")
    async with AsyncSessionLocal() as db:
        user = await get_user_by_id(db, callback.from_user.id)
        if user:
            await set_student_group(db, user.id, group_id)
            await update_notification_setting(db, user.id, notif_enabled)
            await update_schedule_message_type(db, user.id, msg_type)
    await callback.message.edit_text(
        "✅ Регистрация завершена!\n\n"
        "Теперь вы можете:\n"
        "/schedule - расписание на сегодня\n"
        "/tomorrow - расписание на завтра\n"
        "/week - расписание на неделю\n"
        "/settings - настройки\n"
        "/help - помощь"
    )
    await state.clear()
    await callback.answer()

@dp.callback_query(RegState.notification, F.data == "back_format")
async def back_to_format(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("В каком формате вы хотите получать расписание?", reply_markup=format_keyboard())
    await state.set_state(RegState.format)
    await callback.answer()

# ---------- Schedule commands ----------
@dp.message(Command("schedule"))
async def cmd_schedule(message: types.Message):
    async with AsyncSessionLocal() as db:
        user = await get_user_by_platform_id(db, Platform.TELEGRAM, message.from_user.id)
        if not user or (user.teacher_profile_id is None and not user.groups):
            await message.answer("Сначала зарегистрируйтесь: /start")
            return
    await message.answer("📅 Выберите период:", reply_markup=schedule_nav_keyboard())

@dp.callback_query(F.data.startswith("schedule_"))
async def process_schedule_callback(callback: types.CallbackQuery):
    data = callback.data
    user_id = callback.from_user.id
    # Проверка прав (уже зарегистрирован)
    async with AsyncSessionLocal() as db:
        user = await get_user_by_platform_id(db, Platform.TELEGRAM, user_id)
        if not user or (user.teacher_profile_id is None and not user.groups):
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
        async with AsyncSessionLocal() as db:
            user = await get_user_by_id(db, user_id)
            # Для простоты – текстовое расписание на каждый день
            text_parts = []
            delta = timedelta(days=1)
            cur = start_date
            while cur <= end_date:
                day_text = await get_schedule_text_cached(user_id, cur)
                text_parts.append(day_text)
                cur += delta
            full_text = "\n\n".join(text_parts)
            await callback.message.answer(full_text, parse_mode="Markdown")
    else:
        # single day: schedule_YYYY-MM-DD
        date_str = data.split("_")[1]
        target_date = date.fromisoformat(date_str)
        async with AsyncSessionLocal() as db:
            user = await get_user_by_id(db, user_id)
            if user.schedule_message_type == ScheduleMessageType.PICTURE and get_user_role(user) == "student":
                try:
                    img_bytes = await get_schedule_image_cached(user_id, target_date)
                    if img_bytes:
                        await callback.message.answer_photo(
                            BufferedInputFile(img_bytes, filename="schedule.png"),
                            caption=f"Расписание на {target_date.strftime('%d.%m.%Y')}"
                        )
                    else:
                        await callback.message.answer("Не удалось сгенерировать картинку.")
                except Exception as e:
                    await callback.message.answer(f"❌ Ошибка: {e}")
            else:
                text = await get_schedule_text_cached(user_id, target_date)
                await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

@dp.message(Command("tomorrow"))
async def cmd_tomorrow(message: types.Message):
    async with AsyncSessionLocal() as db:
        user = await get_user_by_platform_id(db, Platform.TELEGRAM, message.from_user.id)
        if not user or (user.teacher_profile_id is None and not user.groups):
            await message.answer("Сначала зарегистрируйтесь: /start")
            return
    tomorrow = get_current_date() + timedelta(days=1)
    text = await get_schedule_text_cached(message.from_user.id, tomorrow)
    await message.answer(text, parse_mode="Markdown")

@dp.message(Command("week"))
async def cmd_week(message: types.Message):
    async with AsyncSessionLocal() as db:
        user = await get_user_by_platform_id(db, Platform.TELEGRAM, message.from_user.id)
        if not user or (user.teacher_profile_id is None and not user.groups):
            await message.answer("Сначала зарегистрируйтесь: /start")
            return
    today = get_current_date()
    text_parts = []
    for i in range(7):
        target = today + timedelta(days=i)
        day_text = await get_schedule_text_cached(message.from_user.id, target)
        text_parts.append(day_text)
    full_text = "\n\n".join(text_parts)
    await message.answer(full_text, parse_mode="Markdown")

# ---------- Settings command ----------
@dp.message(Command("settings"))
async def cmd_settings(message: types.Message):
    async with AsyncSessionLocal() as db:
        user = await get_user_by_platform_id(db, Platform.TELEGRAM, message.from_user.id)
        if not user or (user.teacher_profile_id is None and not user.groups):
            await message.answer("Сначала зарегистрируйтесь: /start")
            return
        role = get_user_role(user)
        await message.answer(
            f"⚙️ Настройки\n\n"
            f"Роль: {role}\n"
            f"Уведомления: {'вкл' if user.is_notification_on else 'выкл'}\n"
            f"Формат расписания: {'картинка' if user.schedule_message_type == ScheduleMessageType.PICTURE else 'текст'}\n\n"
            "Для изменения используйте команды:\n"
            "/notify_on - включить уведомления\n"
            "/notify_off - выключить\n"
            "/format_pic - картинкой\n"
            "/format_text - текстом"
        )

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

# ---------- Teacher comment ----------
# Мы не встраиваем кнопки в текст расписания, но преподаватель может написать:
# /comment <id урока> <текст>
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

# Для удобства можно добавить кнопки в расписание, но это сложнее – пока оставим так.

# ---------- Admin command ----------
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

# ---------- Help command ----------
@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    text = (
        "📚 **Помощь**\n\n"
        "/start - начать регистрацию\n"
        "/schedule - расписание на сегодня/завтра/неделю\n"
        "/tomorrow - расписание на завтра\n"
        "/week - расписание на неделю\n"
        "/settings - настройки\n"
        "/notify_on - включить уведомления\n"
        "/notify_off - выключить\n"
        "/format_pic - картинкой\n"
        "/format_text - текстом\n"
        "/comment <id> <текст> - добавить комментарий к занятию (только для преподавателей)\n"
        "/help - это сообщение"
    )
    await message.answer(text)

# ---------- Run bot ----------
async def start_telegram_bot():
    await dp.start_polling(bot, skip_updates=True)
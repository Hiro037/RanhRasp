from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from database.connection import async_session_maker
from services import user_service
from tg_bot.states import RegistrationStates

registration_router = Router()


def get_role_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍🎓 Студент", callback_data="role:student")],
        [InlineKeyboardButton(text="👨‍🏫 Преподаватель", callback_data="role:teacher")]
    ])


def get_format_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Текстовое", callback_data="format:text")],
        [InlineKeyboardButton(text="🖼️ Картинкой", callback_data="format:image")]
    ])


def get_notif_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔔 Включить", callback_data="notif:1")],
        [InlineKeyboardButton(text="🔕 Выключить", callback_data="notif:0")]
    ])


@registration_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Точка входа. Создает пользователя (гостя) и предлагает выбрать роль."""
    async with async_session_maker() as session:
        user = await user_service.get_user_by_platform_id(session, "tg", message.from_user.id)
        if not user:
            await user_service.create_user(session, "tg", message.from_user.id)

    await state.set_state(RegistrationStates.waiting_for_role)
    await message.answer(
        f"Привет, {message.from_user.first_name}! Добро пожаловать в бот расписания.\n"
        "Для начала работы, пожалуйста, укажи, кто ты:",
        reply_markup=get_role_keyboard()
    )


# --- ВЕТКА СТУДЕНТА ---

@registration_router.callback_query(RegistrationStates.waiting_for_role, F.data == "role:student")
async def process_student_role(callback: CallbackQuery, state: FSMContext):
    """Переход на ветку студента: выбор группы."""
    async with async_session_maker() as session:
        groups = await user_service.get_all_groups(session)

    if not groups:
        await callback.message.answer("Ошибка: В базе данных пока нет созданных групп. Обратитесь к админу.")
        await state.clear()
        await callback.answer()
        return

    # Строим клавиатуру групп
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=g.name, callback_data=f"group:{g.id}")] for g in groups
    ])

    await state.set_state(RegistrationStates.waiting_for_group)
    await callback.message.edit_text("Выбери свою учебную группу из списка:", reply_markup=keyboard)
    await callback.answer()


@registration_router.callback_query(RegistrationStates.waiting_for_group, F.data.startswith("group:"))
async def process_student_group(callback: CallbackQuery, state: FSMContext):
    """Сохранение группы и запрос формата расписания."""
    group_id = int(callback.data.split(":")[1])
    await state.update_data(group_id=group_id)

    await state.set_state(RegistrationStates.waiting_for_format)
    await callback.message.edit_text(
        "В каком виде тебе удобнее получать расписание?",
        reply_markup=get_format_keyboard()
    )
    await callback.answer()


@registration_router.callback_query(RegistrationStates.waiting_for_format, F.data.startswith("format:"))
async def process_student_format(callback: CallbackQuery, state: FSMContext):
    """Сохранение формата и запрос уведомлений."""
    sc_format = callback.data.split(":")[1]
    await state.update_data(schedule_format=sc_format)

    await state.set_state(RegistrationStates.waiting_for_notifications)
    await callback.message.edit_text(
        "Включить утренние уведомления с расписанием на день?",
        reply_markup=get_notif_keyboard()
    )
    await callback.answer()


@registration_router.callback_query(RegistrationStates.waiting_for_notifications, F.data.startswith("notif:"))
async def process_student_final(callback: CallbackQuery, state: FSMContext):
    """Финал регистрации студента. Запись всех данных в БД."""
    notif_val = bool(int(callback.data.split(":")[1]))
    user_data = await state.get_data()
    await state.clear()

    async with async_session_maker() as session:
        user = await user_service.get_user_by_platform_id(session, "tg", callback.from_user.id)
        if user:
            # Обновляем профиль в БД через сервисный слой
            await user_service.set_user_group(session, user.id, user_data["group_id"])
            await user_service.update_user_preferences(
                session, user.id,
                msg_type=user_data["schedule_format"],
                notifs_enabled=notif_val
            )

    await callback.message.edit_text(
        "🎉 Регистрация успешно завершена!\n"
        "Твой профиль студента настроен. Нажми /menu для перехода к расписанию."
    )
    await callback.answer()


# --- ВЕТКА ПРЕПОДАВАТЕЛЯ ---

@registration_router.callback_query(RegistrationStates.waiting_for_role, F.data == "role:teacher")
async def process_teacher_role(callback: CallbackQuery, state: FSMContext):
    """Переход на ветку преподавателя: запрос ФИО."""
    await state.set_state(RegistrationStates.waiting_for_teacher_name)
    await callback.message.edit_text(
        "Введите Ваши ФИО (точно так же, как в официальном расписании).\n"
        "Например: *Баянова О.В.*",
        parse_mode="Markdown"
    )
    await callback.answer()


@registration_router.message(RegistrationStates.waiting_for_teacher_name)
async def process_teacher_name(message: Message, state: FSMContext):
    """Прием ФИО и отправка заявки на верификацию (для Этапа 9)."""
    teacher_name = message.text.strip()
    await state.clear()

    # По вашему плану (Этап 9) здесь создается заявка, которая ждет одобрения админом.
    # Пока мы просто запишем ФИО в буфер или профиль со статусом "не верифицирован"
    async with async_session_maker() as session:
        user = await user_service.get_user_by_platform_id(session, "tg", message.from_user.id)
        if user:
            # Кастомный метод сервиса (или создание профиля)
            await user_service.create_teacher_request(session, user.id, teacher_name)

    await message.answer(
        f"Спасибо, {teacher_name}! Ваша заявка на доступ к панели преподавателя отправлена администраторам.\n"
        "После верификации вы получите уведомление и доступ к комментированию занятий."
    )
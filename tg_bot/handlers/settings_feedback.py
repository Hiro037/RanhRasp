from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User, Group
from services.user_service import get_or_create_user, update_user_preferences, update_user_group, create_feedback

router = Router()


class SettingsFeedbackStates(StatesGroup):
    waiting_for_feedback = State()
    waiting_for_new_group = State()


@router.callback_query(F.data == "settings_menu")
async def show_settings(callback: CallbackQuery, session: AsyncSession):
    user = await get_or_create_user(session, "telegram", callback.from_user.id)

    notify_text = "🔔 Включены" if user.is_notification_on else "🔕 Выключены"
    type_text = "🖼 Картинка" if user.schedule_message_type == "pic" else "📝 Текст"

    buttons = [
        [InlineKeyboardButton(text=f"Уведомления: {notify_text}", callback_data="toggle_notify")],
        [InlineKeyboardButton(text=f"Формат: {type_text}", callback_data="toggle_format")]
    ]

    # Если пользователь студент (нет профиля преподавателя), даем возможность сменить группу
    if user.teacher_profile_id is None:
        current_group = user.groups[0].name if user.groups else "Не выбрана"
        buttons.append([InlineKeyboardButton(text=f"🏫 Группа: {current_group}", callback_data="change_user_group")])

    buttons.append([InlineKeyboardButton(text="⬅️ Главное меню", callback_data="main_menu")])

    await callback.message.edit_text("⚙️ **Настройки профиля:**\nИзмените параметры под себя:",
                                     reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data == "toggle_notify")
async def toggle_notifications(callback: CallbackQuery, session: AsyncSession):
    user = await get_or_create_user(session, "telegram", callback.from_user.id)
    new_status = not user.is_notification_on
    await update_user_preferences(session, user.id, is_notification_on=new_status)
    await callback.answer("Настройки уведомлений изменены!")
    await show_settings(callback, session)


@router.callback_query(F.data == "toggle_format")
async def toggle_format_type(callback: CallbackQuery, session: AsyncSession):
    user = await get_or_create_user(session, "telegram", callback.from_user.id)
    new_format = "text" if user.schedule_message_type == "pic" else "pic"
    await update_user_preferences(session, user.id, schedule_type=new_format)
    await callback.answer("Формат расписания изменен!")
    await show_settings(callback, session)


@router.callback_query(F.data == "change_user_group")
async def change_group_start(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    groups_res = await session.execute(select(Group).order_by(Group.name))
    groups = groups_res.scalars().all()

    buttons = []
    for g in groups:
        buttons.append([InlineKeyboardButton(text=g.name, callback_data=f"set_new_group_{g.name}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="settings_menu")])

    await callback.message.edit_text("📋 Выберите вашу новую группу из списка:",
                                     reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("set_new_group_"))
async def change_group_finish(callback: CallbackQuery, session: AsyncSession):
    group_name = callback.data.replace("set_new_group_", "")
    user = await get_or_create_user(session, "telegram", callback.from_user.id)

    success = await update_user_group(session, user.id, group_name)
    if success:
        await callback.answer(f"Группа успешно изменена на {group_name}!", show_alert=True)
    else:
        await callback.answer("Ошибка изменения группы.")
    await show_settings(callback, session)


@router.callback_query(F.data == "feedback_menu")
async def feedback_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SettingsFeedbackStates.waiting_for_feedback)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[[InlineKeyboardButton(text="❌ Отмена", callback_data="main_menu")]]])
    await callback.message.edit_text(
        "💬 Напишите ваше предложение, отзыв или сообщение об ошибке для администрации учебного заведения.\n\n*Отправьте сообщение текстом:*",
        reply_markup=keyboard, parse_mode="Markdown")


@router.message(SettingsFeedbackStates.waiting_for_feedback)
async def feedback_received(message: Message, state: FSMContext, session: AsyncSession):
    if not message.text:
        await message.answer("Пожалуйста, отправьте текстовое сообщение.")
        return

    user = await get_or_create_user(session, "telegram", message.from_user.id)
    await create_feedback(session, user.id, message.text)
    await state.clear()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[[InlineKeyboardButton(text="📱 В главное меню", callback_data="main_menu")]]])
    await message.answer("✅ Ваше обращение успешно сохранено и отправлено администрации! Спасибо за обратную связь.",
                         reply_markup=keyboard)

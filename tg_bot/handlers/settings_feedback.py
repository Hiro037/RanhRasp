from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from sqlalchemy import select

from database.connection import async_session
from services import user_service
from tg_bot.states import RegistrationStates  # не используется, но оставим

router = Router()


class SettingsFeedbackStates(StatesGroup):
    waiting_for_feedback = State()
    waiting_for_new_group = State()


@router.callback_query(F.data == "menu:settings")
async def show_settings(callback: CallbackQuery):
    async with async_session() as session:
        user = await user_service.get_user_by_platform_id(session, "telegram", callback.from_user.id)
        if not user:
            # Создаём, если нет (на всякий случай)
            user = await user_service.create_user(session, "telegram", callback.from_user.id)

        notify_text = "🔔 Включены" if user.is_notification_on else "🔕 Выключены"
        # В БД хранится 'pic' или 'text'
        type_text = "🖼 Картинка" if user.schedule_message_type == "pic" else "📝 Текст"

        buttons = [
            [InlineKeyboardButton(text=f"Уведомления: {notify_text}", callback_data="toggle_notify")],
            [InlineKeyboardButton(text=f"Формат: {type_text}", callback_data="toggle_format")]
        ]

        # Если пользователь студент (нет профиля преподавателя)
        if user.teacher_profile_id is None:
            current_group = user.groups[0].name if user.groups else "Не выбрана"
            buttons.append([InlineKeyboardButton(text=f"🏫 Группа: {current_group}", callback_data="change_user_group")])

        buttons.append([InlineKeyboardButton(text="⬅️ Главное меню", callback_data="menu:back")])

        await callback.message.edit_text(
            "⚙️ **Настройки профиля:**\nИзмените параметры под себя:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await callback.answer()


@router.callback_query(F.data == "toggle_notify")
async def toggle_notifications(callback: CallbackQuery):
    async with async_session() as session:
        user = await user_service.get_user_by_platform_id(session, "telegram", callback.from_user.id)
        if user:
            new_status = not user.is_notification_on
            await user_service.update_user_preferences(session, user.id, is_notification_on=new_status)
            await callback.answer("Настройки уведомлений изменены!")
            await show_settings(callback)
        else:
            await callback.answer("Пользователь не найден", show_alert=True)


@router.callback_query(F.data == "toggle_format")
async def toggle_format_type(callback: CallbackQuery):
    async with async_session() as session:
        user = await user_service.get_user_by_platform_id(session, "telegram", callback.from_user.id)
        if user:
            # Переключаем между 'text' и 'pic'
            new_type = "text" if user.schedule_message_type == "pic" else "pic"
            await user_service.update_user_preferences(session, user.id, schedule_type=new_type)
            await callback.answer("Формат расписания изменен!")
            await show_settings(callback)
        else:
            await callback.answer("Пользователь не найден", show_alert=True)


@router.callback_query(F.data == "change_user_group")
async def change_group_start(callback: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        groups = await user_service.get_all_groups(session)
        if not groups:
            await callback.answer("Нет доступных групп", show_alert=True)
            return

        buttons = []
        for g in groups:
            buttons.append([InlineKeyboardButton(text=g.name, callback_data=f"set_new_group_{g.id}")])
        buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="settings_menu")])

        await callback.message.edit_text(
            "📋 Выберите вашу новую группу из списка:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await callback.answer()


@router.callback_query(F.data.startswith("set_new_group_"))
async def change_group_finish(callback: CallbackQuery):
    group_id = int(callback.data.split("_")[-1])
    async with async_session() as session:
        user = await user_service.get_user_by_platform_id(session, "telegram", callback.from_user.id)
        if user:
            success = await user_service.set_user_group(session, user.id, group_id)
            if success:
                await callback.answer(f"Группа успешно изменена!", show_alert=True)
            else:
                await callback.answer("Ошибка изменения группы.", show_alert=True)
        else:
            await callback.answer("Пользователь не найден", show_alert=True)
    await show_settings(callback)


@router.callback_query(F.data == "menu:feedback")
async def feedback_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SettingsFeedbackStates.waiting_for_feedback)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="main_menu")]]
    )
    await callback.message.edit_text(
        "💬 Напишите ваше предложение, отзыв или сообщение об ошибке для администрации учебного заведения.\n\n*Отправьте сообщение текстом:*",
        reply_markup=keyboard, parse_mode="Markdown"
    )
    await callback.answer()


@router.message(SettingsFeedbackStates.waiting_for_feedback)
async def feedback_received(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Пожалуйста, отправьте текстовое сообщение.")
        return

    async with async_session() as session:
        user = await user_service.get_user_by_platform_id(session, "telegram", message.from_user.id)
        if user:
            await user_service.create_feedback(session, user.id, message.text)
        else:
            # Гость — создаём временного пользователя (но лучше не пускать)
            user = await user_service.create_user(session, "telegram", message.from_user.id)
            await user_service.create_feedback(session, user.id, message.text)

    await state.clear()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📱 В главное меню", callback_data="main_menu")]]
    )
    await message.answer(
        "✅ Ваше обращение успешно сохранено и отправлено администрации! Спасибо за обратную связь.",
        reply_markup=keyboard
    )

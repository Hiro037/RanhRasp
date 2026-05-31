from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from database.connection import async_session_maker
from database.models import User
from services import user_service
from config import settings

tg_settings_router = Router()


class FeedbackStates(StatesGroup):
    waiting_for_feedback = State()


async def get_settings_keyboard(user: User) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру настроек с динамическим отображением текущих статусов."""
    msg_type = "📝 Текст" if user.schedule_message_type == "text" else "🖼️ Картинка"
    notif_status = "🔔 Включены" if user.notifications_enabled else "🔕 Выключены"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📊 Формат: {msg_type}", callback_data="set:toggle_type")],
        [InlineKeyboardButton(text=f"📢 Уведомления: {notif_status}", callback_data="set:toggle_notif")],
        [InlineKeyboardButton(text="✍️ Написать администрации", callback_data="set:feedback")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="menu:back")]
    ])
    return kb


@tg_settings_router.callback_query(F.data == "menu:settings")
async def show_settings(callback: CallbackQuery):
    async with async_session_maker() as session:
        user = await user_service.get_user_by_platform_id(session, "tg", callback.from_user.id)

    if not user:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return

    kb = await get_settings_keyboard(user)
    await callback.message.edit_text("⚙️ *Управление вашим профилем и уведомлениями:*", parse_mode="Markdown",
                                     reply_markup=kb)
    await callback.answer()


@tg_settings_router.callback_query(F.data.startswith("set:toggle_"))
async def toggle_setting_value(callback: CallbackQuery):
    action = callback.data.split("_")[1]

    async with async_session_maker() as session:
        stmt = select(User).where(User.platform == "tg", User.platform_user_id == str(callback.from_user.id))
        res = await session.execute(stmt)
        user = res.scalars().first()

        if user:
            if action == "type":
                user.schedule_message_type = "image" if user.schedule_message_type == "text" else "text"
            elif action == "notif":
                user.notifications_enabled = not user.notifications_enabled
            await session.commit()

            # Обновляем клавиатуру на лету
            kb = await get_settings_keyboard(user)
            await callback.message.edit_reply_markup(reply_markup=kb)
            await callback.answer("✅ Настройки успешно обновлены!")


@tg_settings_router.callback_query(F.data == "set:feedback")
async def start_feedback_flow(callback: CallbackQuery, state: FSMContext):
    await state.set_state(FeedbackStates.waiting_for_feedback)
    await callback.message.edit_text(
        "📥 Напишите ваше сообщение, предложение или жалобу.\n"
        "Оно будет немедленно передано администраторам системы.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:settings")]
        ])
    )
    await callback.answer()


@tg_settings_router.message(FeedbackStates.waiting_for_feedback)
async def process_feedback_message(message: Message, state: FSMContext):
    feedback_text = message.text.strip()
    await state.clear()

    from main_loader import tg_bot

    # Пересылаем сообщение всем админам из конфигурации
    admin_alert = (
        f"📩 *Получен новый отзыв/жалоба!*\n\n"
        f"👤 Отправитель: {message.from_user.full_name} (ID: {message.from_user.id}, @{message.from_user.username or 'нет'})\n"
        f"📱 Платформа: Telegram\n"
        f"💬 Текст: {feedback_text}"
    )

    for admin_id in settings.ADMIN_IDS:
        try:
            await tg_bot.send_message(chat_id=admin_id, text=admin_alert, parse_mode="Markdown")
        except Exception:
            pass  # Если у админа не запущен бот

    await message.answer("✅ Ваше сообщение успешно отправлено! Спасибо за обратную связь.")

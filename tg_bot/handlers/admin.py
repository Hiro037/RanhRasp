import math
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, and_

from database.connection import async_session_maker
from database.models import User
from services import admin_service
from config import settings

admin_router = Router()


def is_admin(user_id: int) -> bool:
    """Проверка прав администратора по ID из конфигурации."""
    return user_id in settings.ADMIN_IDS


@admin_router.message(F.text == "🛠️ Админ-панель")
@admin_router.message(F.text == "/admin")
async def show_admin_panel(message: Message):
    if not is_admin(message.from_user.id): return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика системы", callback_data="admin:stats")],
        [InlineKeyboardButton(text="⏳ Заявки на верификацию", callback_data="admin:pending_users")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="menu:back")]
    ])
    await message.answer("🔑 Панель администратора базы данных расписания:", reply_markup=kb)


@admin_router.callback_query(F.data == "admin:main")
async def back_to_admin_main(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика системы", callback_data="admin:stats")],
        [InlineKeyboardButton(text="⏳ Заявки на верификацию", callback_data="admin:pending_users")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="menu:back")]
    ])
    await callback.message.edit_text("🔑 Панель администратора базы данных расписания:", reply_markup=kb)
    await callback.answer()


@admin_router.callback_query(F.data == "admin:stats")
async def show_statistics(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return

    async with async_session_maker() as session:
        # Твой точный метод сбора статистики
        stats = await admin_service.get_bot_statistics(session)

    text = (
        "📈 *Актуальные показатели активности ботов:*\n\n"
        f"👥 Всего студентов в БД: {stats['students_count']}\n"
        f"👨‍🏫 Преподавателей с профилем: {stats['teachers_count']}\n\n"
        f"📱 Уникальных юзеров сегодня: {stats['active_today']}\n"
        f"📅 Активных за неделю: {stats['active_week']}\n"
        f"📊 Активных за месяц: {stats['active_month']}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin:main")]])
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer()


@admin_router.callback_query(F.data == "admin:pending_users")
async def show_pending_users(callback: CallbackQuery):
    """Выводит пользователей, запросивших роль учителя, у которых нет привязки к профилю."""
    if not is_admin(callback.from_user.id): return

    async with async_session_maker() as session:
        stmt = select(User).where(and_(User.role == "teacher", User.teacher_profile_id.is_(None))).order_by(User.id)
        result = await session.execute(stmt)
        pending_users = result.scalars().all()

    if not pending_users:
        await callback.message.edit_text(
            "🎉 Новых заявок на верификацию преподавателей нет!",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin:main")]])
        )
        await callback.answer()
        return

    builder = InlineKeyboardBuilder()
    for u in pending_users:
        display_name = u.username or f"ID: {u.id}"
        builder.button(text=f"❓ Заявка от {display_name}", callback_data=f"admin:review_user:{u.id}")

    builder.button(text="🔙 В админку", callback_data="admin:main")
    builder.adjust(1)

    await callback.message.edit_text("⏳ Выберите пользователя для верификации:", reply_markup=builder.as_markup())
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin:review_user:"))
async def review_user_request(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    target_user_id = int(callback.data.split(":")[2])

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Связать с профилем",
                                 callback_data=f"admin:paginate_teachers:{target_user_id}:1"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:reject_user:{target_user_id}")
        ],
        [InlineKeyboardButton(text="🔙 К списку заявок", callback_data="admin:pending_users")]
    ])
    await callback.message.edit_text(f"👤 Рассмотрение заявки пользователя ID: {target_user_id}.\nВыберите действие:",
                                     reply_markup=kb)
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin:paginate_teachers:"))
async def show_teachers_pagination_page(callback: CallbackQuery):
    """Архитектурный венец: пагинация ФИО преподавателей из базы по 8 штук."""
    if not is_admin(callback.from_user.id): return

    _, _, target_user_id, page_str = callback.data.split(":")
    target_user_id = int(target_user_id)
    page = int(page_str)
    PER_PAGE = 8

    async with async_session_maker() as session:
        # Твой метод выгрузки всех учителей в алфавитном порядке
        all_teachers = await admin_service.get_teachers_sorted(session)

    total_teachers = len(all_teachers)
    if total_teachers == 0:
        await callback.answer("⚠️ В базе данных расписания нет ни одного преподавателя!", show_alert=True)
        return

    total_pages = math.ceil(total_teachers / PER_PAGE)

    # Срез списка для текущей страницы
    start_idx = (page - 1) * PER_PAGE
    end_idx = start_idx + PER_PAGE
    teachers_slice = all_teachers[start_idx:end_idx]

    builder = InlineKeyboardBuilder()
    for t in teachers_slice:
        # Клик по кнопке конкретного учителя запускает привязку
        builder.button(text=f"👨‍🏫 {t.name}", callback_data=f"admin:link:{target_user_id}:{t.id}")

    builder.adjust(1)

    # Кнопки пагинации
    nav_row = []
    if page > 1:
        nav_row.append(
            InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin:paginate_teachers:{target_user_id}:{page - 1}"))
    nav_row.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="ignore"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Вперед ➡️",
                                            callback_data=f"admin:paginate_teachers:{target_user_id}:{page + 1}"))

    builder.row(*nav_row)
    builder.row(InlineKeyboardButton(text="🔙 Отмена", callback_data=f"admin:review_user:{target_user_id}"))

    await callback.message.edit_text(
        f"📖 Выберите официальный профиль из расписания для сопоставления с пользователем ID {target_user_id}:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin:link:"))
async def process_linking(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    _, _, target_user_id, teacher_id = callback.data.split(":")
    target_user_id = int(target_user_id)
    teacher_id = int(teacher_id)

    from main_loader import tg_bot, vk_bot

    async with async_session_maker() as session:
        # Твой метод связывания аккаунта с фиксацией коммита
        await admin_service.link_teacher_to_user(session, target_user_id, teacher_id)

        # Получаем данные пользователя для отправки уведомления
        stmt = select(User).where(User.id == target_user_id)
        res = await session.execute(stmt)
        user = res.scalars().first()

    await callback.answer("✅ Профиль успешно привязан!")

    if user:
        msg = "🎉 Ваш аккаунт успешно верифицирован! Вам предоставлен доступ к панели преподавателя."
        try:
            if user.platform == "tg":
                await tg_bot.send_message(chat_id=user.platform_user_id, text=msg)
            elif user.platform == "vk":
                await vk_bot.api.messages.send(peer_id=user.platform_user_id, message=msg, random_id=0)
        except Exception as e:
            print(f"Ошибка уведомления пользователя: {e}")

    # Возвращаем админа к списку оставшихся заявок
    await show_pending_users(callback)


@admin_router.callback_query(F.data.startswith("admin:reject_user:"))
async def process_rejection(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    target_user_id = int(callback.data.split(":")[2])

    from main_loader import tg_bot, vk_bot

    async with async_session_maker() as session:
        stmt = select(User).where(User.id == target_user_id)
        res = await session.execute(stmt)
        user = res.scalars().first()
        if user:
            user.role = "student"  # Сбрасываем в дефолтного студента
            await session.commit()

    await callback.answer("❌ Заявка отклонена.")
    if user:
        msg = "⚠️ Ваша заявка на статус преподавателя была отклонена администратором. Вы переведены в статус студента."
        try:
            if user.platform == "tg":
                await tg_bot.send_message(chat_id=user.platform_user_id, text=msg)
            elif user.platform == "vk":
                await vk_bot.api.messages.send(peer_id=user.platform_user_id, message=msg, random_id=0)
        except Exception as e:
            print(e)

    await show_pending_users(callback)
    
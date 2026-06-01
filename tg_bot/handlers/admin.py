from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.models import User, Teacher, TeacherRequest, Feedback
from services.user_service import determine_user_role
from services.paginator import get_page_items
from services.admin_service import get_bot_statistics, get_teachers_sorted, link_teacher_to_user
from database.connection import async_session
from tg_bot.keyboards import get_admin_menu_keyboard

router = Router()


def is_admin(platform_id: int) -> bool:
    return platform_id in settings.TG_ADMINS


@router.callback_query(F.data == "menu:admin_panel")
async def show_admin_panel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет прав администратора.", show_alert=True)
        return
    await callback.message.edit_text(
        "⚙️ **Админ-панель чат-бота**\nВыберите раздел:",
        reply_markup=get_admin_menu_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "admin:stats")
async def show_statistics(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    async with async_session() as session:
        stats = await get_bot_statistics(session)

    text = (
        f"📊 **Статистика системы:**\n\n"
        f"👥 Всего пользователей: {stats['students_count'] + stats['teachers_count']}\n"
        f"👨‍🎓 Студентов: {stats['students_count']}\n"
        f"👨‍🏫 Преподавателей: {stats['teachers_count']}\n\n"
        f"📈 Активность:\n"
        f" ├ За сегодня: {stats['active_today']}\n"
        f" ├ За неделю: {stats['active_week']}\n"
        f" └ За месяц: {stats['active_month']}"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:admin_panel")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "admin:requests")
async def show_requests_menu(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍🏫 Заявки верификации", callback_data="admin:view_teacher_reqs_1")],
        [InlineKeyboardButton(text="💬 Обратная связь", callback_data="admin:view_feedback_1")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:admin_panel")]
    ])
    await callback.message.edit_text(
        "📥 **Раздел запросов**\nВыберите категорию:",
        reply_markup=keyboard
    )
    await callback.answer()


# ---------- ЗАЯВКИ ПРЕПОДАВАТЕЛЕЙ ----------

@router.callback_query(F.data.startswith("admin:view_teacher_reqs_"))
async def view_teacher_requests(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    page = int(callback.data.split("_")[-1])

    async with async_session() as session:
        res = await session.execute(
            select(TeacherRequest)
            .where(TeacherRequest.status == "pending")
            .order_by(TeacherRequest.created_at.desc())
        )
        requests = res.scalars().all()

    if not requests:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:requests")]]
        )
        await callback.message.edit_text("📭 Активных заявок на верификацию нет.", reply_markup=keyboard)
        return

    items, has_prev, has_next = get_page_items(requests, page, page_size=1)
    req = items[0]

    text = (
        f"📝 **Заявка на верификацию ({page}/{len(requests)}):**\n\n"
        f"👤 Аккаунт ID: {req.user_id}\n"
        f"✍️ ФИО: {req.teacher_name}\n"
        f"📅 Дата: {req.created_at.strftime('%d.%m.%Y %H:%M')}"
    )

    nav_buttons = []
    if has_prev:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin:view_teacher_reqs_{page-1}"))
    if has_next:
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"admin:view_teacher_reqs_{page+1}"))

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять", callback_data=f"admin:approve_req_{req.id}_1"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:reject_req_{req.id}")],
        nav_buttons,
        [InlineKeyboardButton(text="⬅️ В меню запросов", callback_data="admin:requests")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("admin:approve_req_"))
async def approve_teacher_request(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    parts = callback.data.split("_")
    req_id = int(parts[2])
    page = int(parts[3])

    async with async_session() as session:
        req = await session.get(TeacherRequest, req_id)
        if not req or req.status != "pending":
            await callback.answer("Заявка не найдена или уже обработана", show_alert=True)
            return

        teachers = await get_teachers_sorted(session)
        items, has_prev, has_next = get_page_items(teachers, page, page_size=8)

        text = f"🔗 **Связывание аккаунта преподавателя**\nЗаявка от: {req.teacher_name}\nВыберите преподавателя из базы (Страница {page}):"

        buttons = []
        for t in items:
            buttons.append([InlineKeyboardButton(text=t.name, callback_data=f"admin:link_teacher_{req.id}_{t.id}")])

        nav_buttons = []
        if has_prev:
            nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin:approve_req_{req_id}_{page-1}"))
        if has_next:
            nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"admin:approve_req_{req_id}_{page+1}"))
        if nav_buttons:
            buttons.append(nav_buttons)
        buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="admin:requests")])

        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()


@router.callback_query(F.data.startswith("admin:link_teacher_"))
async def link_teacher_finish(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    parts = callback.data.split("_")
    req_id = int(parts[2])
    teacher_id = int(parts[3])

    async with async_session() as session:
        req = await session.get(TeacherRequest, req_id)
        teacher = await session.get(Teacher, teacher_id)
        if req and teacher and req.status == "pending":
            req.status = "approved"
            await link_teacher_to_user(session, req.user_id, teacher.id)
            await callback.answer(f"✅ Преподаватель {teacher.name} успешно привязан!", show_alert=True)

            # Уведомляем преподавателя
            user = await session.get(User, req.user_id)
            if user and user.platform == "telegram":
                from tg_bot.loader import tg_bot
                try:
                    await tg_bot.send_message(
                        chat_id=user.platform_id,
                        text="🎉 Ваша заявка на верификацию преподавателя одобрена!\n"
                             "Теперь вы можете добавлять комментарии к занятиям через кнопку '✏️ Добавить комментарий' в расписании."
                    )
                except Exception as e:
                    print(f"Не удалось уведомить преподавателя {user.id}: {e}")
        else:
            await callback.answer("Ошибка при привязке", show_alert=True)

    await show_requests_menu(callback)


@router.callback_query(F.data.startswith("admin:reject_req_"))
async def reject_teacher_request(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    req_id = int(callback.data.split("_")[-1])
    async with async_session() as session:
        req = await session.get(TeacherRequest, req_id)
        if req and req.status == "pending":
            req.status = "rejected"
            await session.commit()
            await callback.answer("❌ Заявка отклонена", show_alert=True)

            # Уведомляем преподавателя
            user = await session.get(User, req.user_id)
            if user and user.platform == "telegram":
                from tg_bot.loader import tg_bot
                try:
                    await tg_bot.send_message(
                        chat_id=user.platform_id,
                        text="😞 Ваша заявка на верификацию преподавателя была отклонена. Свяжитесь с администратором."
                    )
                except Exception:
                    pass
        else:
            await callback.answer("Заявка уже обработана", show_alert=True)

    await show_requests_menu(callback)


# ---------- ОБРАТНАЯ СВЯЗЬ ----------

@router.callback_query(F.data.startswith("admin:view_feedback_"))
async def view_feedback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    page = int(callback.data.split("_")[-1])

    async with async_session() as session:
        res = await session.execute(
            select(Feedback)
            .where(Feedback.is_reviewed.is_(False))
            .order_by(Feedback.created_at.desc())
        )
        feedbacks = res.scalars().all()

    if not feedbacks:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:requests")]]
        )
        await callback.message.edit_text("📭 Нерассмотренной обратной связи нет.", reply_markup=keyboard)
        return

    items, has_prev, has_next = get_page_items(feedbacks, page, page_size=1)
    fb = items[0]

    text = (
        f"💬 **Обратная связь ({page}/{len(feedbacks)}):**\n\n"
        f"👤 От пользователя ID: {fb.user_id}\n"
        f"📝 Сообщение:\n{fb.message}\n\n"
        f"📅 Дата: {fb.created_at.strftime('%d.%m.%Y %H:%M')}"
    )

    nav_buttons = []
    if has_prev:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin:view_feedback_{page-1}"))
    if has_next:
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"admin:view_feedback_{page+1}"))

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отметить как прочитано", callback_data=f"admin:read_fb_{fb.id}")],
        nav_buttons,
        [InlineKeyboardButton(text="⬅️ В меню запросов", callback_data="admin:requests")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("admin:read_fb_"))
async def read_feedback_status(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    fb_id = int(callback.data.split("_")[-1])
    async with async_session() as session:
        fb = await session.get(Feedback, fb_id)
        if fb:
            fb.is_reviewed = True
            await session.commit()
            await callback.answer("✅ Отмечено как прочитанное")
        else:
            await callback.answer("Обращение не найдено")
    await show_requests_menu(callback)
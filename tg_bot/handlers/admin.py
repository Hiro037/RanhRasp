from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import false

from config import Settings
from database.models import User, Teacher, TeacherRequest, Feedback, Logs
from services.user_service import determine_user_role
from services.paginator import get_page_items

router = Router()
settings = Settings()


def is_admin_check(platform_id: int) -> bool:
    return platform_id in settings.TG_ADMINS


@router.callback_query(F.data == "admin_panel")
async def show_admin_panel(callback: CallbackQuery):
    if not is_admin_check(callback.from_user.id):
        await callback.answer("У вас нет прав администратора.", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),   # ← исправлено
         InlineKeyboardButton(text="📥 Запросы", callback_data="admin_requests")],
        [InlineKeyboardButton(text="📱 Главное меню", callback_data="main_menu")]
    ])
    await callback.message.edit_text("⚙️ **Админ-панель чат-бота**\nВыберите интересующий раздел:",
                                     reply_markup=keyboard)


@router.callback_query(F.data == "admin_stats")
async def show_statistics(callback: CallbackQuery, session: AsyncSession):
    if not is_admin_check(callback.from_user.id):
        return

    now = datetime.utcnow()
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    # Собираем общую метрику пользователей
    users_res = await session.execute(select(User))
    all_users = users_res.scalars().all()

    total_count = len(all_users)
    teachers_count = sum(1 for u in all_users if u.teacher_profile_id is not None)
    students_count = total_count - teachers_count

    # Активность пользователей из таблицы логов / активности
    active_today = await session.scalar(select(func.count(User.id)).where(User.last_activity >= day_ago))
    active_week = await session.scalar(select(func.count(User.id)).where(User.last_activity >= week_ago))
    active_month = await session.scalar(select(func.count(User.id)).where(User.last_activity >= month_ago))

    text = (
        f"📊 **Статистика системы:**\n\n"
        f"👥 Всего пользователей: {total_count}\n"
        f"👨‍🎓 Студентов: {students_count}\n"
        f"👨‍🏫 Преподавателей: {teachers_count}\n\n"
        f"📈 Активность:\n"
        f" ├ За сегодня: {active_today}\n"
        f" ├ За неделю: {active_week}\n"
        f" └ За месяц: {active_month}"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data == "admin_requests")
async def show_requests_menu(callback: CallbackQuery):
    if not is_admin_check(callback.from_user.id): return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍🏫 Заявки верификации", callback_data="view_teacher_reqs_1")],
        [InlineKeyboardButton(text="💬 Обратная связь", callback_data="view_feedback_1")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]
    ])
    await callback.message.edit_text("📥 **Раздел запросов**\nВыберите категорию для просмотра:", reply_markup=keyboard)


@router.callback_query(F.data.startswith("view_teacher_reqs_"))
async def view_teacher_requests(callback: CallbackQuery, session: AsyncSession):
    if not is_admin_check(callback.from_user.id): return
    page = int(callback.data.split("_")[-1])

    res = await session.execute(
        select(TeacherRequest).where(TeacherRequest.status == "pending").order_by(TeacherRequest.created_at.desc()))
    requests = res.scalars().all()

    if not requests:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_requests")]])
        await callback.message.edit_text("📭 Активных заявок на верификацию от преподавателей нет.",
                                         reply_markup=keyboard)
        return

    items, has_prev, has_next = get_page_items(requests, page, page_size=1)
    req = items[0]

    text = (
        f"📝 **Заявка на верификацию преподавателя ({page}/{len(requests)}):**\n\n"
        f"👤 Аккаунт: ID {req.user_id} (Платформа: Telegram)\n"
        f"✍️ Введенное ФИО: {req.teacher_name}\n"
        f"📅 Дата подачи: {req.created_at.strftime('%d.%m.%Y %H:%M')}"
    )

    nav_buttons = []
    if has_prev: nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"view_teacher_reqs_{page - 1}"))
    if has_next: nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"view_teacher_reqs_{page + 1}"))

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять", callback_data=f"approve_req_{req.id}_1"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_req_{req.id}")],
        nav_buttons,
        [InlineKeyboardButton(text="⬅️ В меню запросов", callback_data="admin_requests")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("approve_req_"))
async def approve_teacher_request(callback: CallbackQuery, session: AsyncSession):
    if not is_admin_check(callback.from_user.id): return
    parts = callback.data.split("_")
    req_id = int(parts[2])
    page = int(parts[3])

    req = await session.get(TeacherRequest, req_id)
    if not req:
        await callback.answer("Заявка не найдена.")
        return

    teachers_res = await session.execute(select(Teacher).order_by(Teacher.name))
    teachers = teachers_res.scalars().all()

    items, has_prev, has_next = get_page_items(teachers, page, page_size=8)

    text = f"🔗 **Связывание аккаунта преподавателя**\nЗаявка от: {req.teacher_name}\nВыберите соответствующего преподавателя из базы данных (Страница {page}):"

    buttons = []
    for t in items:
        buttons.append([InlineKeyboardButton(text=t.name, callback_data=f"link_teacher_{req.id}_{t.id}")])

    nav_buttons = []
    if has_prev: nav_buttons.append(
        InlineKeyboardButton(text="⏪ Назад", callback_data=f"approve_req_{req_id}_{page - 1}"))
    if has_next: nav_buttons.append(
        InlineKeyboardButton(text="Вперед ⏩", callback_data=f"approve_req_{req_id}_{page + 1}"))

    if nav_buttons:
        buttons.append(nav_buttons)
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="admin_requests")])

    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("link_teacher_"))
async def link_teacher_finish(callback: CallbackQuery, session: AsyncSession):
    if not is_admin_check(callback.from_user.id): return
    parts = callback.data.split("_")
    req_id = int(parts[2])
    t_id = int(parts[3])

    req = await session.get(TeacherRequest, req_id)
    teacher = await session.get(Teacher, t_id)

    if req and teacher:
        req.status = "approved"
        user = await session.get(User, req.user_id)
        if user:
            user.teacher_profile_id = teacher.id
        await session.commit()
        await callback.answer(f"Преподаватель {teacher.name} успешно привязан!", show_alert=True)
    else:
        await callback.answer("Ошибка при привязке", show_alert=True)

    await show_requests_menu(callback)


@router.callback_query(F.data.startswith("reject_req_"))
async def reject_teacher_request(callback: CallbackQuery, session: AsyncSession):
    if not is_admin_check(callback.from_user.id): return
    req_id = int(callback.data.split("_")[-1])
    req = await session.get(TeacherRequest, req_id)
    if req:
        req.status = "rejected"
        await session.commit()
        await callback.answer("Заявка отклонена.")
    await show_requests_menu(callback)


@router.callback_query(F.data.startswith("view_feedback_"))
async def view_feedback(callback: CallbackQuery, session: AsyncSession):
    if not is_admin_check(callback.from_user.id): return
    page = int(callback.data.split("_")[-1])

    res = await session.execute(
        select(Feedback).where(Feedback.is_reviewed.is_(False)).order_by(Feedback.created_at.desc())
    )
    feedbacks = res.scalars().all()

    if not feedbacks:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_requests")]])
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
    if has_prev: nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"view_feedback_{page - 1}"))
    if has_next: nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"view_feedback_{page + 1}"))

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отметить как прочитано", callback_data=f"read_fb_{fb.id}")],
        nav_buttons,
        [InlineKeyboardButton(text="⬅️ В меню запросов", callback_data="admin_requests")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("read_fb_"))
async def read_feedback_status(callback: CallbackQuery, session: AsyncSession):
    if not is_admin_check(callback.from_user.id): return
    fb_id = int(callback.data.split("_")[-1])
    fb = await session.get(Feedback, fb_id)
    if fb:
        fb.is_reviewed = True
        await session.commit()
        await callback.answer("Рассмотрено.")
    await show_requests_menu(callback)
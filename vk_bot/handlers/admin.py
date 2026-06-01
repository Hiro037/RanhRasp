from datetime import datetime, timedelta
from vkbottle.bot import Blueprint, Message
from sqlalchemy import select, func

from database.connection import async_session
from database.models import User, Teacher, TeacherRequest, Feedback
from services.paginator import get_page_items
from config import Settings

bp = Blueprint("AdminHandlers")
settings = Settings()


def is_admin_vk(user_id: int) -> bool:
    return user_id in settings.VK_ADMINS


@bp.on.message(text="Админ-панель")
async def show_admin_panel_vk(message: Message):
    if not is_admin_vk(message.from_id):
        return "У вас нет прав администратора."
    text = (
        "⚙️ Админ-панель чат-бота\n\n"
        "Доступные команды:\n"
        "👉 [Админ статистика] — Просмотр активности пользователей\n"
        "👉 [Админ заявки] — Просмотр заявок преподавателей\n"
        "👉 [Админ фидбек] — Просмотр обратной связи"
    )
    return text


@bp.on.message(text="Админ статистика")
async def stats_vk(message: Message):
    if not is_admin_vk(message.from_id):
        return

    async with async_session() as session:
        now = datetime.utcnow()
        day_ago = now - timedelta(days=1)

        users_res = await session.execute(select(User))
        all_users = users_res.scalars().all()

        total = len(all_users)
        teachers = sum(1 for u in all_users if u.teacher_profile_id is not None)
        students = total - teachers
        active_today = await session.scalar(
            select(func.count(User.id)).where(User.last_activity >= day_ago)
        )

    return (
        f"📊 Статистика:\n"
        f"Всего пользователей: {total}\n"
        f"Студентов: {students}\n"
        f"Преподавателей: {teachers}\n"
        f"Активны сегодня: {active_today}"
    )


# Дополнительные админ-обработчики для заявок и фидбека (по аналогии с Telegram)
@bp.on.message(text="Админ заявки")
async def show_teacher_requests_vk(message: Message):
    if not is_admin_vk(message.from_id):
        return

    async with async_session() as session:
        result = await session.execute(
            select(TeacherRequest)
            .where(TeacherRequest.status == "pending")
            .order_by(TeacherRequest.created_at.desc())
        )
        requests = result.scalars().all()

    if not requests:
        return "📭 Активных заявок на верификацию нет."

    # Пагинация по 1 заявке для простоты (можно расширить)
    page = 1  # Для VK можно хранить состояние, но для простоты показываем первую
    items, has_prev, has_next = get_page_items(requests, page, page_size=1)
    req = items[0]

    text = (
        f"📝 **Заявка на верификацию преподавателя (1/{len(requests)}):**\n\n"
        f"👤 Аккаунт ID: {req.user_id}\n"
        f"✍️ ФИО: {req.teacher_name}\n"
        f"📅 Дата: {req.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
        f"Для одобрения напишите: Одобрить заявку {req.id}\n"
        f"Для отклонения: Отклонить заявку {req.id}"
    )
    return text


@bp.on.message(text=["Одобрить заявку <req_id>", "Отклонить заявку <req_id>"])
async def process_teacher_request_vk(message: Message, req_id: int):
    if not is_admin_vk(message.from_id):
        return

    async with async_session() as session:
        req = await session.get(TeacherRequest, req_id)
        if not req:
            return "❌ Заявка не найдена."

        if "Одобрить" in message.text:
            # Нужно связать с существующим преподавателем (упрощённо: по имени)
            teacher_result = await session.execute(
                select(Teacher).where(Teacher.name == req.teacher_name)
            )
            teacher = teacher_result.scalar_one_or_none()
            if teacher:
                req.status = "approved"
                user = await session.get(User, req.user_id)
                if user:
                    user.teacher_profile_id = teacher.id
                await session.commit()
                return f"✅ Преподаватель {teacher.name} верифицирован."
            else:
                return "❌ Преподаватель с таким именем не найден в базе. Создайте его через парсер."
        else:  # Отклонить
            req.status = "rejected"
            await session.commit()
            return "❌ Заявка отклонена."


@bp.on.message(text="Админ фидбек")
async def show_feedback_vk(message: Message):
    if not is_admin_vk(message.from_id):
        return

    async with async_session() as session:
        result = await session.execute(
            select(Feedback)
            .where(Feedback.is_reviewed.is_(False))
            .order_by(Feedback.created_at.desc())
        )
        feedbacks = result.scalars().all()

    if not feedbacks:
        return "📭 Нерассмотренной обратной связи нет."

    page = 1
    items, has_prev, has_next = get_page_items(feedbacks, page, page_size=1)
    fb = items[0]

    text = (
        f"💬 **Обратная связь (1/{len(feedbacks)}):**\n\n"
        f"👤 От пользователя ID: {fb.user_id}\n"
        f"📝 Сообщение:\n{fb.message}\n\n"
        f"📅 Дата: {fb.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
        f"Чтобы отметить как прочитанное, напишите: Прочитано {fb.id}"
    )
    return text


@bp.on.message(text="Прочитано <fb_id>")
async def mark_feedback_read_vk(message: Message, fb_id: int):
    if not is_admin_vk(message.from_id):
        return

    async with async_session() as session:
        fb = await session.get(Feedback, fb_id)
        if fb:
            fb.is_reviewed = True
            await session.commit()
            return "✅ Обратная связь отмечена как прочитанная."
        return "❌ Обращение не найдено."

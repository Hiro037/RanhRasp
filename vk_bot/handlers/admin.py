from datetime import datetime, timedelta
from vkbottle.bot import Blueprint, Message
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings
from database.connection import async_session
from database.models import User, Teacher, TeacherRequest, Feedback
from services.paginator import get_page_items

bp = Blueprint("AdminHandlers")
settings = Settings()


def is_admin_vk(user_id: int) -> bool:
    return user_id in settings.VK_ADMINS


@bp.on.message(text="Админ-панель")
async def show_admin_panel_vk(message: Message):
    if not is_admin_vk(message.from_id): return "У вас нет прав администратора."
    # Для ВК используем обычный текстовый вывод меню управления
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
    if not is_admin_vk(message.from_id): return

    # Запрашиваем асинхронную сессию из контекста middleware
    # session: AsyncSession = message.ctx_api.session

    async with async_session() as session:

        now = datetime.utcnow()
        day_ago = now - timedelta(days=1)

        users_res = await session.execute(select(User))
        all_users = users_res.scalars().all()

    total = len(all_users)
    teachers = sum(1 for u in all_users if u.teacher_profile_id is not None)
    students = total - teachers
    active_today = await session.scalar(select(func.count(User.id)).where(User.last_activity >= day_ago))

    return (
        f"📊 Статистика:\n"
        f"Всего пользователей: {total}\n"
        f"Студентов: {students}\n"
        f"Преподавателей: {teachers}\n"
        f"Активны сегодня: {active_today}"
    )

# Аналогичные текстовые обработчики под ВК пишутся по такой же схеме,
# исключая падение по полю User.role

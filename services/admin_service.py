from datetime import timedelta
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import User, Log, Teacher
from utils.timezone import get_now


async def get_bot_statistics(session: AsyncSession) -> dict:
    """Собирает агрегированную статистику по активности пользователей."""
    now = get_now()

    # Временные рамки
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=7)
    month_start = today_start - timedelta(days=30)

    # Количество студентов и преподавателей
    stmt_students = select(func.count(User.id)).where(User.teacher_profile_id.is_(None))
    stmt_teachers = select(func.count(User.id)).where(User.teacher_profile_id.is_not(None))

    # Активность по логам
    stmt_active_today = select(func.count(func.distinct(Log.user_id))).where(Log.datetime >= today_start)
    stmt_active_week = select(func.count(func.distinct(Log.user_id))).where(Log.datetime >= week_start)
    stmt_active_month = select(func.count(func.distinct(Log.user_id))).where(Log.datetime >= month_start)

    return {
        "students_count": (await session.execute(stmt_students)).scalars().first() or 0,
        "teachers_count": (await session.execute(stmt_teachers)).scalars().first() or 0,
        "active_today": (await session.execute(stmt_active_today)).scalars().first() or 0,
        "active_week": (await session.execute(stmt_active_week)).scalars().first() or 0,
        "active_month": (await session.execute(stmt_active_month)).scalars().first() or 0,
    }


async def get_teachers_sorted(session: AsyncSession) -> list[Teacher]:
    """Возвращает список всех преподавателей из базы в алфавитном порядке для пагинации."""
    stmt = select(Teacher).order_by(Teacher.name)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def link_teacher_to_user(session: AsyncSession, user_id: int, teacher_id: int) -> None:
    """Связывает аккаунт пользователя с профилем преподавателя после одобрения админом."""
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalars().first()
    if user:
        user.teacher_profile_id = teacher_id
        await session.commit()
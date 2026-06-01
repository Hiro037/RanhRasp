from datetime import timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import User, Logs, Teacher
from utils.timezone import get_now

async def get_bot_statistics(session: AsyncSession) -> dict:
    now = get_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=7)
    month_start = today_start - timedelta(days=30)

    stmt_students = select(func.count(User.id)).where(User.teacher_profile_id.is_(None))
    stmt_teachers = select(func.count(User.id)).where(User.teacher_profile_id.is_not(None))

    stmt_active_today = select(func.count(func.distinct(Logs.user_id))).where(Logs.datetime >= today_start)
    stmt_active_week = select(func.count(func.distinct(Logs.user_id))).where(Logs.datetime >= week_start)
    stmt_active_month = select(func.count(func.distinct(Logs.user_id))).where(Logs.datetime >= month_start)

    return {
        "students_count": (await session.execute(stmt_students)).scalar() or 0,
        "teachers_count": (await session.execute(stmt_teachers)).scalar() or 0,
        "active_today": (await session.execute(stmt_active_today)).scalar() or 0,
        "active_week": (await session.execute(stmt_active_week)).scalar() or 0,
        "active_month": (await session.execute(stmt_active_month)).scalar() or 0,
    }

async def get_teachers_sorted(session: AsyncSession) -> list:
    result = await session.execute(select(Teacher).order_by(Teacher.name))
    return list(result.scalars().all())

async def link_teacher_to_user(session: AsyncSession, user_id: int, teacher_id: int) -> None:
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user:
        user.teacher_profile_id = teacher_id
        await session.commit()
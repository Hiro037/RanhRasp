from datetime import datetime, date, time, timedelta
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import Lesson, LessonGroup, GroupUser, User
from utils.timezone import YEKT_TZ


def _day_bounds(target_date: date) -> tuple[datetime, datetime]:
    """Границы суток target_date в YEKT (занятия хранятся с этим тайзоной)."""
    day_start = datetime.combine(target_date, time.min, tzinfo=YEKT_TZ)
    return day_start, day_start + timedelta(days=1)


def _next_day_start(target_date: date) -> datetime:
    """Начало суток, следующей за target_date, в YEKT."""
    return datetime.combine(target_date + timedelta(days=1), time.min, tzinfo=YEKT_TZ)


async def get_lessons_for_student(
    session: AsyncSession,
    group_id: int,
    target_date: date
) -> list[Lesson]:
    day_start, day_end = _day_bounds(target_date)

    stmt = (
        select(Lesson)
        .join(LessonGroup)
        .where(
            and_(
                LessonGroup.group_id == group_id,
                Lesson.start_datetime >= day_start,
                Lesson.start_datetime < day_end,
            )
        )
        .options(
            selectinload(Lesson.teacher),
            selectinload(Lesson.subject),
            selectinload(Lesson.classroom),
            selectinload(Lesson.groups),
        )
        .order_by(Lesson.start_datetime)
    )

    result = await session.execute(stmt)
    return list(result.scalars().all())

async def get_lessons_for_teacher(
    session: AsyncSession,
    teacher_id: int,
    target_date: date
) -> list[Lesson]:
    day_start, day_end = _day_bounds(target_date)

    stmt = (
        select(Lesson)
        .where(
            and_(
                Lesson.teacher_id == teacher_id,
                Lesson.start_datetime >= day_start,
                Lesson.start_datetime < day_end,
            )
        )
        .options(
            selectinload(Lesson.teacher),
            selectinload(Lesson.subject),
            selectinload(Lesson.classroom),
            selectinload(Lesson.groups),
        )
        .order_by(Lesson.start_datetime)
    )

    result = await session.execute(stmt)
    return list(result.scalars().all())

async def has_lessons_future(session: AsyncSession, target_date: date, group_id: int | None = None, teacher_id: int | None = None) -> bool:
    """Проверяет, есть ли вообще занятия ПОСЛЕ target_date (для скрытия кнопки 'Вперед')."""
    stmt = select(func.count(Lesson.id))
    if group_id:
        stmt = stmt.join(LessonGroup).where(and_(
            LessonGroup.group_id == group_id,
            Lesson.start_datetime >= _next_day_start(target_date),
        ))
    elif teacher_id:
        stmt = stmt.where(and_(
            Lesson.teacher_id == teacher_id,
            Lesson.start_datetime >= _next_day_start(target_date),
        ))
    else:
        return False

    result = await session.execute(stmt)
    return (result.scalars().first() or 0) > 0

async def get_lesson_for_teacher(
    session: AsyncSession,
    lesson_id: int,
    teacher_id: int
) -> Lesson | None:
    """Возвращает занятие только если оно принадлежит указанному преподавателю."""
    stmt = (
        select(Lesson)
        .where(
            and_(
                Lesson.id == lesson_id,
                Lesson.teacher_id == teacher_id,
            )
        )
        .options(
            selectinload(Lesson.subject),
            selectinload(Lesson.teacher),
        )
    )
    result = await session.execute(stmt)
    return result.scalars().first()


async def add_comment_to_lesson(session: AsyncSession, lesson_id: int, comment: str | None) -> None:
    """Записывает или обновляет комментарий преподавателя к занятию."""
    stmt = select(Lesson).where(Lesson.id == lesson_id)
    result = await session.execute(stmt)
    lesson = result.scalars().first()
    if lesson:
        lesson.comment = comment
        await session.commit()


async def get_students_for_lesson_notification(session: AsyncSession, lesson_id: int) -> list[User]:
    """
    Находит всех пользователей (студентов), которые записаны в группы,
    связанные с конкретным занятием (lesson_id).
    """
    # 1. Находим все group_id, которые есть у этого занятия
    groups_query = select(LessonGroup.group_id).where(LessonGroup.lesson_id == lesson_id)

    # 2. Находим всех пользователей, которые состоят в этих группах
    # distinct(): студент в нескольких группах одного занятия не должен получить уведомление дважды
    query = (
        select(User)
        .join(GroupUser, User.id == GroupUser.user_id)
        .where(GroupUser.group_id.in_(groups_query))
        .where(User.is_notification_on == True)  # Рассылаем только тем, кто включил уведомления
        .distinct()
    )

    result = await session.execute(query)
    return result.scalars().all()
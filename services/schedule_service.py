from datetime import datetime, date
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import Lesson, LessonGroup, GroupUser, User

async def get_lessons_for_student(session: AsyncSession, group_id: int, target_date: date) -> list[Lesson]:
    """Получает список занятий для конкретной группы на выбранную дату."""
    stmt = (
        select(Lesson)
        .join(LessonGroup)
        .where(
            and_(
                LessonGroup.group_id == group_id,
                func.date(Lesson.start_datetime) == target_date
            )
        )
        .options(selectinload(Lesson.groups)) # подгружаем связанные объекты, если нужно
        .order_by(Lesson.start_datetime)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())

async def get_lessons_for_teacher(session: AsyncSession, teacher_id: int, target_date: date) -> list[Lesson]:
    """Получает список занятий для преподавателя на выбранную дату."""
    stmt = (
        select(Lesson)
        .where(
            and_(
                Lesson.teacher_id == teacher_id,
                func.date(Lesson.start_datetime) == target_date
            )
        )
        .order_by(Lesson.start_datetime)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())

async def has_lessons_future(session: AsyncSession, target_date: date, group_id: int | None = None, teacher_id: int | None = None) -> bool:
    """Проверяет, есть ли вообще занятия ПОСЛЕ target_date (для скрытия кнопки 'Вперед')."""
    stmt = select(func.count(Lesson.id))
    if group_id:
        stmt = stmt.join(LessonGroup).where(and_(LessonGroup.group_id == group_id, func.date(Lesson.start_datetime) > target_date))
    elif teacher_id:
        stmt = stmt.where(and_(Lesson.teacher_id == teacher_id, func.date(Lesson.start_datetime) > target_date))
    else:
        return False

    result = await session.execute(stmt)
    return (result.scalars().first() or 0) > 0

async def add_comment_to_lesson(session: AsyncSession, lesson_id: int, comment: str | None) -> None:
    """Записывает или обновляет комментарий преподавателя к занятию."""
    stmt = select(Lesson).where(Lesson.id == lesson_id)
    result = await session.execute(stmt)
    lesson = result.scalars().first()
    if lesson:
        lesson.comment = comment
        await session.commit()

async def get_students_to_notify_by_lesson(session: AsyncSession, lesson_id: int) -> list[User]:
    """Находит всех пользователей (студентов), чьи группы присутствуют на этом занятии."""
    stmt = (
        select(User)
        .join(GroupUser, GroupUser.user_id == User.id)
        .join(LessonGroup, LessonGroup.group_id == GroupUser.group_id)
        .where(LessonGroup.lesson_id == lesson_id)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
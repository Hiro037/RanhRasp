from datetime import datetime
from typing import Sequence
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import User, Group, GroupUser, TeacherRequest, Feedback, Teacher
from config import Settings

settings = Settings()


async def get_or_create_user(session: AsyncSession, platform: str, platform_id: int) -> User:
    """
    Получает пользователя по его platform_id или создает нового, если его нет в базе.
    Сразу подгружает связанные группы и профиль преподавателя для избежания LazyLoad-ошибок.
    """
    query = (
        select(User)
        .where(and_(User.platform == platform, User.platform_id == platform_id))
        .options(selectinload(User.groups), selectinload(User.teacher))
    )
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            platform=platform,
            platform_id=platform_id,
            is_notification_on=True,
            schedule_message_type="text"
        )
        session.add(user)
        await session.commit()
        # Повторно запрашиваем со связями, чтобы объект был валидным
        result = await session.execute(query)
        user = result.scalar_one_or_none()

    return user


async def determine_user_role(user: User) -> str:
    """
    Динамически определяет роль пользователя согласно ТЗ.
    Возвращает: 'admin', 'teacher' или 'student'.
    """
    if user.platform == "telegram" and user.platform_id in settings.TG_ADMINS:
        return "admin"
    if user.platform == "vk" and user.platform_id in settings.VK_ADMINS:
        return "admin"
    if user.teacher_profile_id is not None:
        return "teacher"
    return "student"


async def update_user_preferences(
        session: AsyncSession,
        user_id: int,
        schedule_type: str = None,
        is_notification_on: bool = None
) -> None:
    """Обновляет настройки отображения расписания и уведомлений пользователя"""
    update_data = {}
    if schedule_type is not None:
        update_data["schedule_message_type"] = schedule_type
    if is_notification_on is not None:
        update_data["is_notification_on"] = is_notification_on

    if update_data:
        update_data["last_activity"] = datetime.utcnow()
        query = update(User).where(User.id == user_id).values(**update_data)
        await session.execute(query)
        await session.commit()


async def update_user_group(session: AsyncSession, user_id: int, group_name: str) -> bool:
    """
    Привязывает студента к группе (создает или обновляет запись в group_users).
    Используется как при первичной регистрации, так и при смене группы в настройках.
    """
    # Находим ID группы по её названию
    group_query = select(Group).where(Group.name == group_name)
    group_res = await session.execute(group_query)
    group = group_res.scalar_one_or_none()

    if not group:
        return False  # Группа не найдена в базе данных

    # Удаляем старые привязки к группам (согласно ТЗ у пользователя может быть одна активная группа)
    delete_query = update(GroupUser).where(GroupUser.user_id == user_id)
    # В SQLAlchemy для composite primary key проще удалить старую связь и залить новую
    from sqlalchemy import delete
    await session.execute(delete(GroupUser).where(GroupUser.user_id == user_id))

    # Добавляем новую связь
    new_link = GroupUser(user_id=user_id, group_id=group.id)
    session.add(new_link)

    # Обновляем активность пользователя
    await session.execute(
        update(User).where(User.id == user_id).values(last_activity=datetime.utcnow())
    )

    await session.commit()
    return True


async def create_teacher_request(session: AsyncSession, user_id: int, teacher_name: str) -> TeacherRequest:
    """
    ДОБАВЛЕНО: Создает заявку на верификацию преподавателя.
    Вызывается на Этапе 6 в процессе FSM-регистрации.
    """
    request = TeacherRequest(
        user_id=user_id,
        teacher_name=teacher_name,
        status="pending"
    )
    session.add(request)
    await session.execute(
        update(User).where(User.id == user_id).values(last_activity=datetime.utcnow())
    )
    await session.commit()
    return request


async def create_feedback(session: AsyncSession, user_id: int, message: str) -> Feedback:
    """
    ДОБАВЛЕНО: Сохраняет обращение пользователя (обратную связь) в базу данных.
    Вызывается на Этапе 10 в хендлерах обратной связи.
    """
    feedback = Feedback(
        user_id=user_id,
        message=message,
        is_reviewed=False
    )
    session.add(feedback)
    await session.execute(
        update(User).where(User.id == user_id).values(last_activity=datetime.utcnow())
    )
    await session.commit()
    return feedback


async def update_user_activity(session: AsyncSession, user_id: int) -> None:
    """Обновляет только временную метку последней активности пользователя (для Middleware логирования)"""
    query = update(User).where(User.id == user_id).values(last_activity=datetime.utcnow())
    await session.execute(query)
    await session.commit()
    
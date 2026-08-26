from datetime import datetime
from typing import Sequence
from sqlalchemy import select, update, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import User, Group, GroupUser, TeacherRequest, Feedback, Teacher
from config import Settings
from utils.timezone import YEKT_TZ

settings = Settings()


# ========== БАЗОВЫЕ МЕТОДЫ ==========

async def get_user_by_platform_id(session: AsyncSession, platform: str, platform_id: int) -> User | None:
    """
    Получает пользователя по платформе и ID на платформе.
    Подгружает группы и преподавателя.
    """
    query = (
        select(User)
        .where(and_(User.platform == platform, User.platform_id == platform_id))
        .options(selectinload(User.groups), selectinload(User.teacher))
    )
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def create_user(session: AsyncSession, platform: str, platform_id: int) -> User:
    """Создаёт нового пользователя с настройками по умолчанию."""
    user = User(
        platform=platform,
        platform_id=platform_id,
        is_notification_on=True,
        schedule_message_type="text"
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def get_or_create_user(session: AsyncSession, platform: str, platform_id: int) -> User:
    """Получает пользователя или создаёт нового. Подгружает связи."""
    user = await get_user_by_platform_id(session, platform, platform_id)
    if not user:
        user = await create_user(session, platform, platform_id)
        # Повторно загружаем со связями
        user = await get_user_by_platform_id(session, platform, platform_id)
    return user


async def get_all_groups(session: AsyncSession) -> list[Group]:
    """Возвращает список всех групп, отсортированных по имени."""
    result = await session.execute(select(Group).order_by(Group.name))
    return list(result.scalars().all())


async def get_group_by_id(session: AsyncSession, group_id: int) -> Group | None:
    """Получает группу по ID."""
    result = await session.execute(select(Group).where(Group.id == group_id))
    return result.scalar_one_or_none()


async def get_group_by_name(session: AsyncSession, group_name: str) -> Group | None:
    """Получает группу по названию."""
    result = await session.execute(select(Group).where(Group.name == group_name))
    return result.scalar_one_or_none()


async def determine_user_role(user: User) -> str:
    """Динамически определяет роль пользователя: admin, teacher, student."""
    #if user.platform == "telegram" and user.platform_id in settings.TG_ADMINS:
     #   return "admin"
    #if user.platform == "vk" and user.platform_id in settings.VK_ADMINS:
     #   return "admin"
    if user.teacher_profile_id is not None:
        return "teacher"
    return "student"


# ========== НАСТРОЙКИ ==========

async def update_user_preferences(
    session: AsyncSession,
    user_id: int,
    schedule_type: str | None = None,
    is_notification_on: bool | None = None
) -> None:
    """
    Обновляет настройки отображения расписания и уведомлений пользователя.
    Параметры: schedule_type = 'text' или 'image' (в БД хранится 'text'/'pic')
               is_notification_on = True/False
    """
    update_data = {}
    if schedule_type is not None:
        # Приводим к формату БД
        db_type = "pic" if schedule_type == "pic" else "text"
        update_data["schedule_message_type"] = db_type
    if is_notification_on is not None:
        update_data["is_notification_on"] = is_notification_on

    if update_data:
        update_data["last_activity"] = datetime.now(YEKT_TZ)
        query = update(User).where(User.id == user_id).values(**update_data)
        await session.execute(query)
        await session.commit()


async def update_user_activity(session: AsyncSession, user_id: int) -> None:
    """Обновляет метку последней активности пользователя."""
    query = update(User).where(User.id == user_id).values(last_activity=datetime.now(YEKT_TZ))
    await session.execute(query)
    await session.commit()


# ========== РАБОТА С ГРУППАМИ (MANY-TO-MANY) ==========

async def set_user_group(session: AsyncSession, user_id: int, group_id: int) -> bool:
    """
    Привязывает пользователя к группе (заменяет все предыдущие группы).
    Возвращает True, если группа существует.
    """
    # Проверяем существование группы
    group = await get_group_by_id(session, group_id)
    if not group:
        return False

    # Удаляем старые связи
    await session.execute(delete(GroupUser).where(GroupUser.user_id == user_id))

    # Добавляем новую связь
    new_link = GroupUser(user_id=user_id, group_id=group_id)
    session.add(new_link)
    await session.commit()
    return True


async def update_user_group(session: AsyncSession, user_id: int, group_name: str) -> bool:
    """
    Привязывает пользователя к группе по названию.
    Используется для обратной совместимости со старым кодом.
    """
    group = await get_group_by_name(session, group_name)
    if not group:
        return False
    return await set_user_group(session, user_id, group.id)


async def get_user_group(user: User) -> Group | None:
    """Возвращает первую группу пользователя или None."""
    return user.groups[0] if user.groups else None


# ========== ЗАЯВКИ ПРЕПОДАВАТЕЛЕЙ ==========

async def create_teacher_request(session: AsyncSession, user_id: int, teacher_name: str) -> TeacherRequest:
    """Создаёт заявку на верификацию преподавателя."""
    request = TeacherRequest(
        user_id=user_id,
        teacher_name=teacher_name,
        status="pending"
    )
    session.add(request)
    await session.execute(
        update(User).where(User.id == user_id).values(last_activity=datetime.now(YEKT_TZ))
    )
    await session.commit()
    return request


# ========== ОБРАТНАЯ СВЯЗЬ ==========

async def create_feedback(session: AsyncSession, user_id: int, message: str) -> Feedback:
    """Сохраняет обращение пользователя."""
    feedback = Feedback(
        user_id=user_id,
        message=message,
        is_reviewed=False
    )
    session.add(feedback)
    await session.execute(
        update(User).where(User.id == user_id).values(last_activity=datetime.now(YEKT_TZ))
    )
    await session.commit()
    return feedback
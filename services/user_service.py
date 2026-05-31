from sqlalchemy import select, delete, insert
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import User, Group, GroupUser


async def get_user_by_platform_id(session: AsyncSession, platform: str, platform_id: int) -> User | None:
    """Находит пользователя по его ID внутри конкретной платформы (TG/VK)."""
    stmt = select(User).where(User.platform == platform, User.platform_id == platform_id)
    result = await session.execute(stmt)
    return result.scalars().first()


async def create_user(session: AsyncSession, platform: str, platform_id: int) -> User:
    """Создает нового пользователя (первичный запуск /start)."""
    new_user = User(platform=platform, platform_id=platform_id)
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)
    return new_user


async def get_all_groups(session: AsyncSession) -> list[Group]:
    """Возвращает список всех групп для выбора при регистрации."""
    stmt = select(Group).order_by(Group.name)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def set_user_group(session: AsyncSession, user_id: int, group_id: int) -> None:
    """Привязывает студента к группе (удаляя старые привязки, если они были)."""
    # Удаляем прошлые группы пользователя (так как у нас один студент — одна группа)
    del_stmt = delete(GroupUser).where(GroupUser.user_id == user_id)
    await session.execute(del_stmt)

    # Добавляем новую группу
    ins_stmt = insert(GroupUser).values(user_id=user_id, group_id=group_id)
    await session.execute(ins_stmt)
    await session.commit()


async def get_user_group_id(session: AsyncSession, user_id: int) -> int | None:
    """Получает ID группы, в которой состоит студент."""
    stmt = select(GroupUser.group_id).where(GroupUser.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalars().first()


async def update_user_preferences(
        session: AsyncSession,
        user_id: int,
        is_notification_on: bool,
        schedule_message_type: str
) -> None:
    """Обновляет настройки уведомлений и формата расписания."""
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalars().first()
    if user:
        user.is_notification_on = is_notification_on
        user.schedule_message_type = schedule_message_type
        await session.commit()
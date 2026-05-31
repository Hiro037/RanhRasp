from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import Log

async def add_log_entry(
    session: AsyncSession,
    platform: str,
    action_type: str,
    status: str,
    user_id: int | None = None,
    platform_user_id: int | None = None,
    user_role: str = "guest",
    details: str | None = None
) -> None:
    """Сохраняет запись о действии пользователя в таблицу логов."""
    stmt = insert(Log).values(
        user_id=user_id,
        platform_user_id=platform_user_id,
        user_role=user_role,
        platform=platform,
        action_type=action_type,
        status=status,
        details=details
    )
    await session.execute(stmt)
    await session.commit()
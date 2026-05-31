from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from config import settings

# Создаем асинхронный движок для работы с БД
engine = create_async_engine(settings.DATABASE_URL, echo=False)

# Фабрика для создания короткоживущих сессий
async_session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Асинхронный генератор сессий для использования в хендлерах и сервисах."""
    async with async_session_maker() as session:
        yield session
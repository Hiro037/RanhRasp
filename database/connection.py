from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from config import Settings
from database.models import Base

settings = Settings()

# Создаем асинхронный движок базы данных
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,  # Можно поставить True для отладки SQL-запросов в консоли
    future=True
)

# Фабрика сессий
async_session = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Асинхронный генератор сессий для использования в хендлерах и сервисах"""
    async with async_session() as session:
        yield session

async def init_db() -> None:
    """Функция для первичной инициализации таблиц базы данных"""
    async with engine.begin() as conn:
        # Создает таблицы, если они еще не существуют в базе данных
        await conn.run_sync(Base.metadata.create_all)
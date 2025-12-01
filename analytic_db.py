import asyncio
import os
from datetime import datetime

from dotenv import load_dotenv
from sqlalchemy import BigInteger, String, DateTime, Text
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

load_dotenv()

DB_URL = os.getenv("ANALYTIC_DB_URL")

class Base(AsyncAttrs, DeclarativeBase):
    pass


class UserRequestLog(Base):
    __tablename__ = 'user_requests'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(255), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=True)

    def __repr__(self):
        return f"<UserRequestLog(user_id={self.user_id}, text={self.text[:30] if self.text else None})>"

engine = create_async_engine(DB_URL, echo=False)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# asyncio.run(init_db())
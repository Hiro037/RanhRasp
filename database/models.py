"""
Асинхронные модели для основной БД
"""
import os
from datetime import datetime
from typing import Optional, List

from dotenv import load_dotenv
from sqlalchemy import String, ForeignKey, DateTime, Text, BigInteger
from sqlalchemy.ext.asyncio import AsyncAttrs, create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

load_dotenv()

DB_URL = os.getenv("DB_URL")


# Важно: для SQLite async используем aiosqlite://
# Для PostgreSQL: postgresql+asyncpg://
# Для MySQL: mysql+aiomysql://

class Base(AsyncAttrs, DeclarativeBase):
    """Базовая модель с async поддержкой"""
    pass


# ========== МОДЕЛЬ ПОЛЬЗОВАТЕЛЯ (НОВАЯ!) ==========

class User(Base):
    """
    Модель пользователя бота

    Хранит информацию о пользователях и их взаимодействии с ботом
    """
    __tablename__ = 'users'

    # Основные поля
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        nullable=False,
        index=True,
        comment="Telegram user ID"
    )
    username: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Telegram username"
    )

    # Группа пользователя (связь с Group)
    group_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey('groups.group_id', ondelete='SET NULL'),
        nullable=True,
        index=True,
        comment="Группа пользователя"
    )
    group: Mapped[Optional["Group"]] = relationship(
        "Group",
        back_populates="students",
        lazy="selectin"
    )

    # Метаданные
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        nullable=False
    )
    last_activity: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
        nullable=False
    )

    # Статистика
    total_requests: Mapped[int] = mapped_column(
        default=0,
        comment="Общее количество запросов"
    )

    # Связь с запросами пользователя
    requests: Mapped[List["UserRequest"]] = relationship(
        "UserRequest",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    def __repr__(self):
        return f"<User(id={self.id}, user_id={self.user_id}, username={self.username}, group={self.group.group_name if self.group else None})>"


# ========== МОДЕЛЬ ЗАПРОСОВ ПОЛЬЗОВАТЕЛЯ (НОВАЯ!) ==========

class UserRequest(Base):
    """
    Модель запросов пользователей к боту

    Логирует все взаимодействия пользователей
    """
    __tablename__ = 'user_requests'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Связь с пользователем
    user_id: Mapped[int] = mapped_column(
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    user: Mapped["User"] = relationship("User", back_populates="requests", lazy="selectin")

    # Данные запроса
    request_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Тип запроса: command, callback, schedule_view, etc."
    )
    request_data: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Текст запроса или JSON с данными"
    )

    # Группа на момент запроса (может отличаться от текущей)
    group_snapshot: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Группа пользователя на момент запроса"
    )

    # Метаданные
    timestamp: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        nullable=False,
        index=True
    )

    def __repr__(self):
        return f"<UserRequest(id={self.id}, user_id={self.user_id}, type={self.request_type}, timestamp={self.timestamp})>"


# ========== СУЩЕСТВУЮЩИЕ МОДЕЛИ (ОБНОВЛЕННЫЕ) ==========

class Group(Base):
    """
    Модель учебной группы
    """
    __tablename__ = 'groups'

    group_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    group_name: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True
    )

    # Связь со студентами (новая!)
    students: Mapped[List["User"]] = relationship(
        "User",
        back_populates="group",
        lazy="selectin"
    )

    # Связь с занятиями
    lessons: Mapped[List["Lesson"]] = relationship(
        "Lesson",
        back_populates="group",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    def __repr__(self):
        return f"<Group(id={self.group_id}, name={self.group_name})>"


class Teacher(Base):
    """
    Модель преподавателя
    """
    __tablename__ = 'teachers'

    teacher_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True
    )

    # Потенциал для расширения
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Связь с занятиями
    lessons: Mapped[List["Lesson"]] = relationship(
        "Lesson",
        back_populates="teacher",
        lazy="selectin"
    )

    def __repr__(self):
        return f"<Teacher(id={self.teacher_id}, name={self.name})>"


class Subject(Base):
    """
    Модель учебного предмета
    """
    __tablename__ = 'subjects'

    subject_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True
    )

    # Связь с занятиями
    lessons: Mapped[List["Lesson"]] = relationship(
        "Lesson",
        back_populates="subject",
        lazy="selectin"
    )

    def __repr__(self):
        return f"<Subject(id={self.subject_id}, name={self.name})>"


class Lesson(Base):
    """
    Модель занятия
    """
    __tablename__ = 'lessons'

    lesson_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Временные параметры
    start_datetime: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True
    )
    end_datetime: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True
    )

    # Связи с другими сущностями
    group_id: Mapped[int] = mapped_column(
        ForeignKey('groups.group_id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    group: Mapped["Group"] = relationship("Group", back_populates="lessons", lazy="selectin")

    teacher_id: Mapped[int] = mapped_column(
        ForeignKey('teachers.teacher_id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    teacher: Mapped["Teacher"] = relationship("Teacher", back_populates="lessons", lazy="selectin")

    subject_id: Mapped[int] = mapped_column(
        ForeignKey('subjects.subject_id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    subject: Mapped["Subject"] = relationship("Subject", back_populates="lessons", lazy="selectin")

    # Дополнительные данные
    classroom: Mapped[str] = mapped_column(String(50), nullable=False)
    lesson_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Лекция, семинар, практика и т.д."
    )

    def __repr__(self):
        return f"<Lesson(id={self.lesson_id}, subject={self.subject.name if self.subject else None}, group={self.group.group_name if self.group else None})>"


# ========== ИНИЦИАЛИЗАЦИЯ БД ==========

# Создание асинхронного движка
engine = create_async_engine(
    DB_URL,
    echo=False,  # Логирование SQL запросов (для отладки)
    pool_size=10,  # Размер пула соединений
    max_overflow=20,  # Максимальное количество дополнительных соединений
    pool_pre_ping=True,  # Проверка соединения перед использованием
    pool_recycle=3600  # Переиспользование соединений (1 час)
)

# Создание фабрики асинхронных сессий
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Не удалять объекты из сессии после коммита
    autoflush=False  # Контролируем flush вручную
)


# ========== ИНИЦИАЛИЗАЦИЯ БД ==========

async def init_db():
    """
    Создание всех таблиц в БД

    Вызывается при старте приложения
    """
    async with engine.begin() as conn:
        # Можно добавить удаление таблиц для dev окружения
        # await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    print("✅ База данных инициализирована")


# ========== DEPENDENCY INJECTION ==========

async def get_session() -> AsyncSession:
    """
    Dependency для получения async сессии БД

    Использование в FastAPI:
    @app.get("/")
    async def handler(session: AsyncSession = Depends(get_session)):
        ...
    """
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()

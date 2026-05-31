from datetime import datetime
from sqlalchemy import String, Integer, Boolean, ForeignKey, DateTime, PrimaryKeyConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from utils.timezone import get_now

class Base(DeclarativeBase):
    """Базовый класс для всех моделей."""
    pass

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(10)) # 'tg' или 'vk'
    platform_id: Mapped[int] = mapped_column(Integer, unique=True)
    teacher_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("teachers.id", ondelete="SET NULL"),
        unique=True,
        nullable=True
    )
    is_notification_on: Mapped[bool] = mapped_column(Boolean, default=True)
    schedule_message_type: Mapped[str] = mapped_column(String(10), default="text") # 'text' или 'pic'
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=get_now)
    last_activity: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=get_now, onupdate=get_now)

    # Связи
    teacher_profile = relationship("Teacher", back_populates="user_profile")
    groups = relationship("Group", secondary="group_users", back_populates="users")

class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)

    # Связи
    users = relationship("User", secondary="group_users", back_populates="groups")
    lessons = relationship("Lesson", secondary="lesson_groups", back_populates="groups")

class GroupUser(Base):
    """Связующая таблица для защиты от дублей Студент <-> Группа"""
    __tablename__ = "group_users"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "group_id"),
    )

class Classroom(Base):
    __tablename__ = "classrooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)

class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True)

class Teacher(Base):
    __tablename__ = "teachers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True) # ФИО преподавателя

    # Связи
    user_profile = relationship("User", back_populates="teacher_profile", uselist=False)

class Lesson(Base):
    __tablename__ = "lessons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    start_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    type: Mapped[str] = mapped_column(String(30)) # Лекция, практика и т.д.
    classroom_id: Mapped[int | None] = mapped_column(ForeignKey("classrooms.id", ondelete="SET NULL"))
    teacher_id: Mapped[int | None] = mapped_column(ForeignKey("teachers.id", ondelete="SET NULL"))
    subject_id: Mapped[int | None] = mapped_column(ForeignKey("subjects.id", ondelete="SET NULL"))
    comment: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Связи
    groups = relationship("Group", secondary="lesson_groups", back_populates="lessons")

class LessonGroup(Base):
    """Связующая таблица Многие-ко-Многим для Лекций на несколько групп"""
    __tablename__ = "lesson_groups"

    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"))
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))

    __table_args__ = (
        PrimaryKeyConstraint("lesson_id", "group_id"),
    )

class Log(Base):
    __tablename__ = "logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Делаем Nullable и добавляем сырые ID платформы, чтобы не падать, если юзера еще нет в таблице users
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    platform_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_role: Mapped[str] = mapped_column(String(20), default="guest") # guest, student, teacher, admin
    platform: Mapped[str] = mapped_column(String(10)) # 'tg' или 'vk'
    datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=get_now)
    action_type: Mapped[str] = mapped_column(String(50)) # 'command_start', 'click_schedule'
    status: Mapped[str] = mapped_column(String(20)) # 'success', 'error'
    details: Mapped[str | None] = mapped_column(String(1000), nullable=True)
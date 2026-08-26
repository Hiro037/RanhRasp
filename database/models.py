from datetime import datetime
from sqlalchemy import Integer, String, Boolean, DateTime, ForeignKey, PrimaryKeyConstraint, Text, BigInteger
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from utils.timezone import YEKT_TZ


def _now_yekt() -> datetime:
    """Текущее время в YEKT (aware), чтобы не писать наивные UTC-даты."""
    return datetime.now(YEKT_TZ)

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(10))  # 'vk' или 'telegram'
    platform_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    teacher_profile_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("teachers.id", ondelete="SET NULL"), unique=True, nullable=True
    )
    is_notification_on: Mapped[bool] = mapped_column(Boolean, default=True)
    schedule_message_type: Mapped[str] = mapped_column(String(10), default="text")  # 'pic' или 'text'
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_yekt)
    last_activity: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_yekt, onupdate=_now_yekt)

    # Связи
    teacher: Mapped["Teacher | None"] = relationship("Teacher", back_populates="user")
    groups: Mapped[list["Group"]] = relationship("Group", secondary="group_users", back_populates="users")
    logs: Mapped[list["Logs"]] = relationship("Logs", back_populates="user")
    teacher_requests: Mapped[list["TeacherRequest"]] = relationship("TeacherRequest", back_populates="user")
    feedbacks: Mapped[list["Feedback"]] = relationship("Feedback", back_populates="user")

class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    # Связи
    users: Mapped[list["User"]] = relationship("User", secondary="group_users", back_populates="groups")
    lessons: Mapped[list["Lesson"]] = relationship("Lesson", secondary="lesson_groups", back_populates="groups")

class GroupUser(Base):
    __tablename__ = "group_users"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("groups.id", ondelete="CASCADE"))

    __table_args__ = (
        PrimaryKeyConstraint("user_id", group_id),
    )

class Classroom(Base):
    __tablename__ = "classrooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    # Связи
    lessons: Mapped[list["Lesson"]] = relationship("Lesson", back_populates="classroom")

class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)

    # Связи
    lessons: Mapped[list["Lesson"]] = relationship("Lesson", back_populates="subject")

class Teacher(Base):
    __tablename__ = "teachers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    # Связи
    user: Mapped["User | None"] = relationship("User", back_populates="teacher")
    lessons: Mapped[list["Lesson"]] = relationship("Lesson", back_populates="teacher")

class Lesson(Base):
    __tablename__ = "lessons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    start_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # лекция, практика, консультация и т.д.
    classroom_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("classrooms.id", ondelete="SET NULL"))
    teacher_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("teachers.id", ondelete="SET NULL"))
    subject_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("subjects.id", ondelete="SET NULL"))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Связи
    classroom: Mapped["Classroom | None"] = relationship("Classroom", back_populates="lessons")
    teacher: Mapped["Teacher | None"] = relationship("Teacher", back_populates="lessons")
    subject: Mapped["Subject | None"] = relationship("Subject", back_populates="lessons")
    groups: Mapped[list["Group"]] = relationship("Group", secondary="lesson_groups", back_populates="lessons")

class LessonGroup(Base):
    __tablename__ = "lesson_groups"

    lesson_id: Mapped[int] = mapped_column(Integer, ForeignKey("lessons.id", ondelete="CASCADE"))
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("groups.id", ondelete="CASCADE"))

    __table_args__ = (
        PrimaryKeyConstraint("lesson_id", group_id),
    )

# НОВАЯ ТАБЛИЦА: Заявки на верификацию преподавателей
class TeacherRequest(Base):
    __tablename__ = "teacher_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    teacher_name: Mapped[str] = mapped_column(String(100), nullable=False)  # ФИО, которое ввел пользователь
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, approved, rejected
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_yekt)

    # Связи
    user: Mapped["User"] = relationship("User", back_populates="teacher_requests")

# НОВАЯ ТАБЛИЦА: Хранение обратной связи от пользователей
class Feedback(Base):
    __tablename__ = "feedbacks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_yekt)
    is_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)  # Рассмотрено админом или нет

    # Связи
    user: Mapped["User"] = relationship("User", back_populates="feedbacks")

class Logs(Base):
    __tablename__ = "logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    user_role: Mapped[str] = mapped_column(String(20), default="student")  # Определяется динамически при логировании
    platform: Mapped[str] = mapped_column(String(10), nullable=False)
    platform_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_yekt)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # success, error
    details: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Связи
    user: Mapped["User | None"] = relationship("User", back_populates="logs")

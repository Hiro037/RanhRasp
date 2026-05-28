from datetime import datetime
from sqlalchemy import Integer, String, Boolean, DateTime, ForeignKey, Enum as SQLEnum, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
import enum
import pytz

TZ = pytz.timezone("Asia/Yekaterinburg")

def get_current_time():
    return datetime.now(TZ)

class Base(DeclarativeBase):
    pass

class LessonType(str, enum.Enum):
    LECTURE = "лекция"
    PRACTICE = "практика"
    CONSULTATION = "консультация"
    EXAM = "экзамен"
    CREDIT = "зачет"
    CREDIT_WITH_GRADE = "зачет с оценкой"
    OTHER = "другое"

class ScheduleMessageType(str, enum.Enum):
    PICTURE = "pic"
    TEXT = "text"

class Platform(str, enum.Enum):
    TELEGRAM = "telegram"
    VK = "vk"

class LogStatus(str, enum.Enum):
    SUCCESS = "success"
    ERROR = "error"

class Teacher(Base):
    __tablename__ = "teachers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)

    lessons: Mapped[list["Lesson"]] = relationship(back_populates="teacher")
    users: Mapped[list["User"]] = relationship(back_populates="teacher_profile")

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)
    vk_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    teacher_profile_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_notification_on: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    schedule_message_type: Mapped[ScheduleMessageType] = mapped_column(SQLEnum(ScheduleMessageType), nullable=False, default=ScheduleMessageType.TEXT)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=get_current_time)
    last_activity: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=get_current_time, onupdate=get_current_time)

    teacher_profile: Mapped[Teacher | None] = relationship(back_populates="users")
    groups: Mapped[list["Group"]] = relationship(secondary="group_user", back_populates="users")
    logs: Mapped[list["Log"]] = relationship(back_populates="user")

    __table_args__ = (Index("idx_users_teacher_profile", "teacher_profile_id"),)

class Group(Base):
    __tablename__ = "groups"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)

    users: Mapped[list[User]] = relationship(secondary="group_user", back_populates="groups")
    lessons: Mapped[list["Lesson"]] = relationship(secondary="lesson_groups", back_populates="groups")

class GroupUser(Base):
    __tablename__ = "group_user"
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True)
    __table_args__ = (
        Index("idx_group_user_user", "user_id"),
        Index("idx_group_user_group", "group_id"),
    )

class Classroom(Base):
    __tablename__ = "classrooms"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    lessons: Mapped[list["Lesson"]] = relationship(back_populates="classroom")

class Subject(Base):
    __tablename__ = "subjects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    lessons: Mapped[list["Lesson"]] = relationship(back_populates="subject")

class Lesson(Base):
    __tablename__ = "lessons"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    start_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    type: Mapped[LessonType] = mapped_column(SQLEnum(LessonType), nullable=False)
    classroom_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("classrooms.id", ondelete="SET NULL"), nullable=True)
    teacher_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True)
    subject_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True)
    comment: Mapped[str | None] = mapped_column(String, nullable=True)

    classroom: Mapped[Classroom | None] = relationship(back_populates="lessons")
    teacher: Mapped[Teacher | None] = relationship(back_populates="lessons")
    subject: Mapped[Subject | None] = relationship(back_populates="lessons")
    groups: Mapped[list[Group]] = relationship(secondary="lesson_groups", back_populates="lessons")

    __table_args__ = (
        Index("idx_lesson_teacher", "teacher_id"),
        Index("idx_lesson_classroom", "classroom_id"),
        Index("idx_lesson_subject", "subject_id"),
        Index("idx_lesson_start_datetime", "start_datetime"),
    )

class LessonGroup(Base):
    __tablename__ = "lesson_groups"
    lesson_id: Mapped[int] = mapped_column(Integer, ForeignKey("lessons.id", ondelete="CASCADE"), primary_key=True)
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True)
    __table_args__ = (
        Index("idx_lesson_group_lesson", "lesson_id"),
        Index("idx_lesson_group_group", "group_id"),
    )

class Log(Base):
    __tablename__ = "logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    platform: Mapped[Platform] = mapped_column(SQLEnum(Platform), nullable=False)
    datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=get_current_time)
    action_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[LogStatus] = mapped_column(SQLEnum(LogStatus), nullable=False)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    user: Mapped[User | None] = relationship(back_populates="logs")
    __table_args__ = (
        Index("idx_logs_user", "user_id"),
        Index("idx_logs_datetime", "datetime"),
    )
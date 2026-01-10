"""
User Domain Entity

Представляет пользователя системы (студента или преподавателя).
Независим от SQLAlchemy и других фреймворков.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from enum import Enum


class UserType(str, Enum):
    """Тип пользователя"""
    STUDENT = "student"
    TEACHER = "teacher"


@dataclass
class User:
    """
    Aggregate Root для пользователя

    Содержит бизнес-логику для работы с пользователями.
    """

    # Identity
    id: Optional[int]  # None для новых пользователей
    user_id: int  # Telegram ID
    username: Optional[str]

    # Type and status
    user_type: UserType
    is_verified: bool = False

    # Relationships (IDs, не объекты!)
    group_id: Optional[int] = None
    teacher_id: Optional[int] = None

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    total_requests: int = 0

    # Domain events (не в БД)
    _events: List = field(default_factory=list, repr=False)

    def __post_init__(self):
        """Валидация после создания"""
        self._validate()

    def _validate(self):
        """Валидация бизнес-правил"""
        if self.user_id <= 0:
            raise ValueError("user_id must be positive")

        if self.user_type == UserType.STUDENT and self.group_id is None:
            # Студент без группы — допустимо (выберет позже)
            pass

        if self.user_type == UserType.TEACHER and self.teacher_id is None:
            # Преподаватель без связи с Teacher — пока не зарегистрирован
            pass

    # ========== BUSINESS LOGIC ==========

    def is_student(self) -> bool:
        """Является ли пользователь студентом"""
        return self.user_type == UserType.STUDENT

    def is_teacher(self) -> bool:
        """Является ли пользователь преподавателем"""
        return self.user_type == UserType.TEACHER

    def can_add_comments(self) -> bool:
        """Может ли пользователь добавлять комментарии к занятиям"""
        return self.is_teacher() and self.is_verified

    def verify(self) -> None:
        """
        Верифицировать пользователя (для преподавателей)

        Raises:
            ValueError: если пользователь не преподаватель
        """
        if not self.is_teacher():
            raise ValueError("Only teachers can be verified")

        if self.is_verified:
            raise ValueError("Teacher already verified")

        self.is_verified = True

        # Генерируем событие (будет обработано в application layer)
        from domain.events.user_events import UserVerifiedEvent
        self._events.append(
            UserVerifiedEvent(
                user_id=self.id,
                telegram_id=self.user_id,
                timestamp=datetime.now()
            )
        )

    def change_group(self, new_group_id: int) -> None:
        """
        Сменить группу (для студентов)

        Args:
            new_group_id: ID новой группы

        Raises:
            ValueError: если пользователь не студент
        """
        if not self.is_student():
            raise ValueError("Only students can change groups")

        if new_group_id <= 0:
            raise ValueError("Invalid group_id")

        old_group_id = self.group_id
        self.group_id = new_group_id

        # Генерируем событие
        from domain.events.user_events import UserGroupChangedEvent
        self._events.append(
            UserGroupChangedEvent(
                user_id=self.id,
                old_group_id=old_group_id,
                new_group_id=new_group_id,
                timestamp=datetime.now()
            )
        )

    def record_activity(self) -> None:
        """Обновить время последней активности"""
        self.last_activity = datetime.now()
        self.total_requests += 1

    def link_teacher(self, teacher_id: int) -> None:
        """
        Связать пользователя с преподавателем

        Args:
            teacher_id: ID преподавателя

        Raises:
            ValueError: если пользователь не преподаватель
        """
        if not self.is_teacher():
            raise ValueError("Only teachers can be linked to teacher entities")

        if teacher_id <= 0:
            raise ValueError("Invalid teacher_id")

        self.teacher_id = teacher_id

    # ========== DOMAIN EVENTS ==========

    def get_uncommitted_events(self) -> List:
        """Получить и очистить неопубликованные события"""
        events = self._events.copy()
        self._events.clear()
        return events

    def __repr__(self):
        return (
            f"<User(id={self.id}, user_id={self.user_id}, "
            f"type={self.user_type.value}, verified={self.is_verified})>"
        )

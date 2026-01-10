"""
User Domain Events

События, связанные с пользователями.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from domain.events.domain_event import DomainEvent


@dataclass(frozen=True, kw_only=True)
class UserCreatedEvent(DomainEvent):
    """
    Событие: пользователь зарегистрирован

    Генерируется при создании нового пользователя.
    """

    user_id: int  # Internal ID
    telegram_id: int  # Telegram ID
    user_type: str  # "student" или "teacher"
    username: Optional[str] = None

    def to_dict(self) -> dict:
        """Сериализация события"""
        data = super().to_dict()
        data.update({
            "user_id": self.user_id,
            "telegram_id": self.telegram_id,
            "user_type": self.user_type,
            "username": self.username,
        })
        return data


@dataclass(frozen=True, kw_only=True)
class UserVerifiedEvent(DomainEvent):
    """
    Событие: пользователь верифицирован

    Генерируется когда преподаватель проходит верификацию.
    """

    user_id: int  # Internal ID
    telegram_id: int  # Telegram ID
    verified_by: Optional[int] = None  # ID администратора, кто верифицировал

    def to_dict(self) -> dict:
        """Сериализация события"""
        data = super().to_dict()
        data.update({
            "user_id": self.user_id,
            "telegram_id": self.telegram_id,
            "verified_by": self.verified_by,
        })
        return data


@dataclass(frozen=True, kw_only=True)
class UserGroupChangedEvent(DomainEvent):
    """
    Событие: пользователь сменил группу

    Генерируется когда студент меняет группу.
    """

    user_id: int  # Internal ID
    old_group_id: Optional[int]  # Предыдущая группа (может быть None)
    new_group_id: int  # Новая группа

    def to_dict(self) -> dict:
        """Сериализация события"""
        data = super().to_dict()
        data.update({
            "user_id": self.user_id,
            "old_group_id": self.old_group_id,
            "new_group_id": self.new_group_id,
        })
        return data


@dataclass(frozen=True, kw_only=True)
class UserActivityRecordedEvent(DomainEvent):
    """
    Событие: зафиксирована активность пользователя

    Генерируется при каждом взаимодействии с ботом.
    """

    user_id: int  # Internal ID
    telegram_id: int  # Telegram ID
    request_type: str  # Тип запроса (command, callback, etc.)

    def to_dict(self) -> dict:
        """Сериализация события"""
        data = super().to_dict()
        data.update({
            "user_id": self.user_id,
            "telegram_id": self.telegram_id,
            "request_type": self.request_type,
        })
        return data

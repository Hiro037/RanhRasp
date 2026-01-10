"""
Teacher Domain Events

События, связанные с преподавателями.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from domain.events.domain_event import DomainEvent


@dataclass(frozen=True, kw_only=True)
class TeacherRegisteredEvent(DomainEvent):
    """
    Событие: преподаватель зарегистрирован в системе

    Генерируется при добавлении нового преподавателя.
    """

    teacher_id: int  # ID преподавателя
    teacher_name: str  # ФИО преподавателя
    registered_by: Optional[int] = None  # Кто зарегистрировал

    def to_dict(self) -> dict:
        """Сериализация события"""
        data = super().to_dict()
        data.update({
            "teacher_id": self.teacher_id,
            "teacher_name": self.teacher_name,
            "registered_by": self.registered_by,
        })
        return data


@dataclass(frozen=True, kw_only=True)
class TeacherLinkedToUserEvent(DomainEvent):
    """
    Событие: преподаватель привязан к аккаунту пользователя

    Генерируется когда преподаватель связывается с Telegram аккаунтом.
    """

    teacher_id: int  # ID преподавателя
    user_account_id: int  # ID пользователя (User.id)
    telegram_id: int  # Telegram ID

    def to_dict(self) -> dict:
        """Сериализация события"""
        data = super().to_dict()
        data.update({
            "teacher_id": self.teacher_id,
            "user_account_id": self.user_account_id,
            "telegram_id": self.telegram_id,
        })
        return data


@dataclass(frozen=True, kw_only=True)
class TeacherVerifiedEvent(DomainEvent):
    """
    Событие: преподаватель верифицирован

    Генерируется после прохождения верификации.
    """

    teacher_id: int  # ID преподавателя
    user_account_id: int  # ID пользователя
    verified_by: Optional[int] = None  # ID администратора

    def to_dict(self) -> dict:
        """Сериализация события"""
        data = super().to_dict()
        data.update({
            "teacher_id": self.teacher_id,
            "user_account_id": self.user_account_id,
            "verified_by": self.verified_by,
        })
        return data


@dataclass(frozen=True, kw_only=True)
class TeacherContactInfoUpdatedEvent(DomainEvent):
    """
    Событие: обновлена контактная информация преподавателя

    Генерируется при изменении email/phone.
    """

    teacher_id: int  # ID преподавателя
    updated_fields: list[str]  # ["email", "phone"]

    def to_dict(self) -> dict:
        """Сериализация события"""
        data = super().to_dict()
        data.update({
            "teacher_id": self.teacher_id,
            "updated_fields": self.updated_fields,
        })
        return data

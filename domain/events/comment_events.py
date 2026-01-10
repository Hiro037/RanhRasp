"""
Comment Domain Events

События, связанные с комментариями к занятиям.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List

from domain.events.domain_event import DomainEvent


@dataclass(frozen=True, kw_only=True)
class CommentAddedEvent(DomainEvent):
    """
    Событие: комментарий добавлен к занятию

    Генерируется когда преподаватель добавляет комментарий.
    """

    comment_id: Optional[int]  # ID комментария (может быть None до сохранения)
    lesson_id: int  # ID занятия
    teacher_id: int  # ID преподавателя
    comment_text: str  # Текст комментария
    group_ids: List[int]

    def to_dict(self) -> dict:
        """Сериализация события"""
        data = super().to_dict()
        data.update({
            "comment_id": self.comment_id,
            "lesson_id": self.lesson_id,
            "teacher_id": self.teacher_id,
            "comment_text": self.comment_text[:100] + "..." if len(self.comment_text) > 100 else self.comment_text,
            "group_ids": self.group_ids,
        })
        return data


@dataclass(frozen=True, kw_only=True)
class CommentUpdatedEvent(DomainEvent):
    """
    Событие: комментарий обновлен

    Генерируется при изменении текста комментария.
    """

    comment_id: int  # ID комментария
    lesson_id: int  # ID занятия
    teacher_id: int  # ID преподавателя
    old_text: str  # Старый текст
    new_text: str  # Новый текст

    def to_dict(self) -> dict:
        """Сериализация события"""
        data = super().to_dict()
        data.update({
            "comment_id": self.comment_id,
            "lesson_id": self.lesson_id,
            "teacher_id": self.teacher_id,
            "old_text_preview": self.old_text[:50] + "...",
            "new_text_preview": self.new_text[:50] + "...",
        })
        return data


@dataclass(frozen=True, kw_only=True)
class CommentDeletedEvent(DomainEvent):
    """
    Событие: комментарий удален (скрыт)

    Генерируется при деактивации комментария.
    """

    comment_id: int  # ID комментария
    lesson_id: int  # ID занятия
    teacher_id: int  # ID преподавателя
    deleted_by: Optional[int] = None  # Кто удалил (может отличаться от teacher_id)

    def to_dict(self) -> dict:
        """Сериализация события"""
        data = super().to_dict()
        data.update({
            "comment_id": self.comment_id,
            "lesson_id": self.lesson_id,
            "teacher_id": self.teacher_id,
            "deleted_by": self.deleted_by,
        })
        return data

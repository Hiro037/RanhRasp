"""
Lesson Domain Events

События, связанные с занятиями.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List

from domain.events.domain_event import DomainEvent


@dataclass(frozen=True, kw_only=True)
class LessonCreatedEvent(DomainEvent):
    """
    Событие: создано новое занятие

    Генерируется при добавлении занятия в расписание.
    """

    lesson_id: int  # ID занятия
    group_ids: List[int]  # ID групп
    teacher_id: int  # ID преподавателя
    subject_id: int  # ID предмета
    start_time: datetime  # Начало занятия
    end_time: datetime  # Конец занятия

    def to_dict(self) -> dict:
        """Сериализация события"""
        data = super().to_dict()
        data.update({
            "lesson_id": self.lesson_id,
            "group_ids": self.group_ids,
            "teacher_id": self.teacher_id,
            "subject_id": self.subject_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
        })
        return data


@dataclass(frozen=True, kw_only=True)
class LessonUpdatedEvent(DomainEvent):
    """
    Событие: занятие обновлено

    Генерируется при изменении параметров занятия.
    """

    lesson_id: int  # ID занятия
    group_ids: List[int]  # ID групп
    changed_fields: list[str]  # Список измененных полей

    def to_dict(self) -> dict:
        """Сериализация события"""
        data = super().to_dict()
        data.update({
            "lesson_id": self.lesson_id,
            "group_ids": self.group_ids,
            "changed_fields": self.changed_fields,
        })
        return data


@dataclass(frozen=True, kw_only=True)
class LessonCancelledEvent(DomainEvent):
    """
    Событие: занятие отменено

    Генерируется при отмене занятия.
    """

    lesson_id: int  # ID занятия
    group_id: int  # ID группы
    teacher_id: int  # ID преподавателя
    subject_id: int  # ID предмета
    cancelled_by: Optional[int] = None  # Кто отменил
    cancellation_reason: Optional[str] = None  # Причина отмены

    def to_dict(self) -> dict:
        """Сериализация события"""
        data = super().to_dict()
        data.update({
            "lesson_id": self.lesson_id,
            "group_id": self.group_id,
            "teacher_id": self.teacher_id,
            "subject_id": self.subject_id,
            "cancelled_by": self.cancelled_by,
            "cancellation_reason": self.cancellation_reason,
        })
        return data


@dataclass(frozen=True, kw_only=True)
class LessonStartedEvent(DomainEvent):
    """
    Событие: занятие началось

    Генерируется автоматически по расписанию (триггер).
    """

    lesson_id: int  # ID занятия
    group_id: int  # ID группы
    teacher_id: int  # ID преподавателя
    subject_id: int  # ID предмета

    def to_dict(self) -> dict:
        """Сериализация события"""
        data = super().to_dict()
        data.update({
            "lesson_id": self.lesson_id,
            "group_id": self.group_id,
            "teacher_id": self.teacher_id,
            "subject_id": self.subject_id,
        })
        return data


@dataclass(frozen=True, kw_only=True)
class LessonEndedEvent(DomainEvent):
    """
    Событие: занятие завершилось

    Генерируется автоматически по расписанию (триггер).
    """

    lesson_id: int  # ID занятия
    group_id: int  # ID группы
    teacher_id: int  # ID преподавателя
    subject_id: int  # ID предмета

    def to_dict(self) -> dict:
        """Сериализация события"""
        data = super().to_dict()
        data.update({
            "lesson_id": self.lesson_id,
            "group_id": self.group_id,
            "teacher_id": self.teacher_id,
            "subject_id": self.subject_id,
        })
        return data

@dataclass(frozen=True, kw_only=True)
class GroupAddedToLessonEvent(DomainEvent):
    """
    Событие: группа добавлена к занятию (стало совмещенным)

    Генерируется когда к занятию добавляется еще одна группа.
    """

    lesson_id: int
    group_id: int  # Добавленная группа
    all_group_ids: List[int]  # Все группы после добавления

    def to_dict(self) -> dict:
        """Сериализация события"""
        data = super().to_dict()
        data.update({
            "lesson_id": self.lesson_id,
            "group_id": self.group_id,
            "all_group_ids": self.all_group_ids,
        })
        return data


@dataclass(frozen=True, kw_only=True)
class GroupRemovedFromLessonEvent(DomainEvent):
    """
    Событие: группа удалена из совмещенного занятия

    Генерируется когда группа убирается из совмещенного занятия.
    """

    lesson_id: int
    group_id: int  # Удаленная группа
    remaining_group_ids: List[int]  # Оставшиеся группы

    def to_dict(self) -> dict:
        """Сериализация события"""
        data = super().to_dict()
        data.update({
            "lesson_id": self.lesson_id,
            "group_id": self.group_id,
            "remaining_group_ids": self.remaining_group_ids,
        })
        return data

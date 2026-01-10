"""
Lesson Domain Aggregate

Занятие с возможностью добавления комментариев.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from domain.entities.comment import Comment
from domain.value_objects.time_slot import TimeSlot
from domain.value_objects.classroom import Classroom


@dataclass(kw_only=True)
class Lesson:
    """
    Aggregate Root для занятия

    Управляет комментариями и бизнес-логикой занятий.
    """

    # Identity
    id: Optional[int]  # None для новых занятий

    # Time and place
    time_slot: TimeSlot
    classroom: Classroom
    lesson_type: Optional[str] = None  # "Лекция", "Семинар", "Практика"

    # Relationships (IDs, не объекты!)
    group_ids: List[int] = field(default_factory=list)
    teacher_id: int
    subject_id: int

    # Aggregated entities
    comments: List[Comment] = field(default_factory=list)

    # Domain events
    _events: List = field(default_factory=list, repr=False)

    def __post_init__(self):
        """Валидация после создания"""
        if not self.group_ids or len(self.group_ids) == 0:
            raise ValueError("Lesson must have at least one group")

        # Убираем дубликаты
        object.__setattr__(self, 'group_ids', list(set(self.group_ids)))

        self._validate()

    def _validate(self):
        """Валидация бизнес-правил"""
        for group_id in self.group_ids:
            if group_id <= 0:
                raise ValueError("Invalid group_id")

        if self.teacher_id <= 0:
            raise ValueError("Invalid teacher_id")

        if self.subject_id <= 0:
            raise ValueError("Invalid subject_id")

        if not self.time_slot.is_valid():
            raise ValueError("Invalid time slot: end must be after start")

    # ========== BUSINESS LOGIC ==========

    def is_combined_lesson(self) -> bool:
        """Является ли занятие совмещенным (для нескольких групп)"""
        return len(self.group_ids) > 1

    def has_group(self, group_id: int) -> bool:
        """Участвует ли группа в этом занятии"""
        return group_id in self.group_ids

    def get_all_group_ids(self) -> List[int]:
        """Получить все ID групп"""
        return self.group_ids.copy()

    def add_group(self, group_id: int) -> None:
        """
        Добавить группу к занятию (сделать совмещенным)

        Args:
            group_id: ID группы для добавления

        Raises:
            ValueError: если группа уже добавлена
        """
        if group_id <= 0:
            raise ValueError("Invalid group_id")

        if group_id in self.group_ids:
            raise ValueError(f"Group {group_id} already added to lesson")

        self.group_ids.append(group_id)

        # Генерируем событие
        from domain.events.lesson_events import GroupAddedToLessonEvent
        self._events.append(
            GroupAddedToLessonEvent(
                lesson_id=self.id,
                group_id=group_id,
                all_group_ids=self.group_ids.copy(),
                timestamp=datetime.now()
            )
        )

    def remove_group(self, group_id: int) -> None:
        """
        Убрать группу из занятия

        Args:
            group_id: ID группы для удаления

        Raises:
            ValueError: если это последняя группа или группа не найдена
        """
        if group_id not in self.group_ids:
            raise ValueError(f"Group {group_id} not found in lesson")

        if len(self.group_ids) == 1:
            raise ValueError("Cannot remove last group from lesson")

        self.group_ids.remove(group_id)

        # Генерируем событие
        from domain.events.lesson_events import GroupRemovedFromLessonEvent
        self._events.append(
            GroupRemovedFromLessonEvent(
                lesson_id=self.id,
                group_id=group_id,
                remaining_group_ids=self.group_ids.copy(),
                timestamp=datetime.now()
            )
        )

    def add_comment(self, teacher_id: int, text: str) -> Comment:
        """
        Добавить комментарий к занятию

        Args:
            teacher_id: ID преподавателя
            text: Текст комментария

        Returns:
            Созданный комментарий

        Raises:
            ValueError: если преподаватель не ведет это занятие
        """
        # Бизнес-правило: только преподаватель занятия может комментировать
        if teacher_id != self.teacher_id:
            raise ValueError("Only the lesson teacher can add comments")

        # Создаем комментарий
        comment = Comment(
            id=None,  # Будет заполнено при сохранении
            text=text,
            lesson_id=self.id,
            teacher_id=teacher_id,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            is_active=True
        )

        self.comments.append(comment)

        # Генерируем событие
        from domain.events.comment_events import CommentAddedEvent
        self._events.append(
            CommentAddedEvent(
                lesson_id=self.id,
                teacher_id=teacher_id,
                comment_id=comment.id,
                comment_text=text,
                group_ids=self.group_ids.copy(),
                timestamp=datetime.now()
            )
        )

        return comment

    def get_active_comments(self) -> List[Comment]:
        """Получить только активные (видимые) комментарии"""
        return [c for c in self.comments if c.is_active]

    def has_comments(self) -> bool:
        """Есть ли активные комментарии"""
        return len(self.get_active_comments()) > 0

    def is_in_progress(self, current_time: datetime) -> bool:
        """Идет ли занятие прямо сейчас"""
        return self.time_slot.contains(current_time)

    def is_upcoming(self, current_time: datetime) -> bool:
        """Будущее ли занятие"""
        return self.time_slot.start > current_time

    def is_past(self, current_time: datetime) -> bool:
        """Прошедшее ли занятие"""
        return self.time_slot.end < current_time

    # ========== DOMAIN EVENTS ==========

    def get_uncommitted_events(self) -> List:
        """Получить и очистить неопубликованные события"""
        events = self._events.copy()
        self._events.clear()
        return events

    def __repr__(self):
        return (
            f"<Lesson(id={self.id}, subject_id={self.subject_id}, "
            f"time={self.time_slot})>"
        )

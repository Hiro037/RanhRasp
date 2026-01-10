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


@dataclass
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
    group_id: int
    teacher_id: int
    subject_id: int

    # Aggregated entities
    comments: List[Comment] = field(default_factory=list)

    # Domain events
    _events: List = field(default_factory=list, repr=False)

    def __post_init__(self):
        """Валидация после создания"""
        self._validate()

    def _validate(self):
        """Валидация бизнес-правил"""
        if self.group_id <= 0:
            raise ValueError("Invalid group_id")

        if self.teacher_id <= 0:
            raise ValueError("Invalid teacher_id")

        if self.subject_id <= 0:
            raise ValueError("Invalid subject_id")

        if not self.time_slot.is_valid():
            raise ValueError("Invalid time slot: end must be after start")

    # ========== BUSINESS LOGIC ==========

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

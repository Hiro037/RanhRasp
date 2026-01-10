"""
Comment Domain Value Object

Комментарий преподавателя к занятию.
Immutable (неизменяемый).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)  # frozen=True делает immutable
class Comment:
    """
    Value Object для комментария

    Комментарии неизменяемы после создания.
    Если нужно изменить — создаем новый комментарий.
    """

    # Identity
    id: Optional[int]  # None для новых комментариев

    # Content
    text: str

    # Relationships (IDs)
    lesson_id: int
    teacher_id: int

    # Metadata
    created_at: datetime
    updated_at: datetime
    is_active: bool = True

    def __post_init__(self):
        """Валидация (даже для frozen dataclass можно через object.__setattr__)"""
        if not self.text or len(self.text.strip()) == 0:
            raise ValueError("Comment text cannot be empty")

        if len(self.text) > 5000:
            raise ValueError("Comment text too long (max 5000 chars)")

        if self.lesson_id <= 0:
            raise ValueError("Invalid lesson_id")

        if self.teacher_id <= 0:
            raise ValueError("Invalid teacher_id")

    def is_visible(self) -> bool:
        """Виден ли комментарий студентам"""
        return self.is_active

    def __repr__(self):
        return (
            f"<Comment(id={self.id}, lesson_id={self.lesson_id}, "
            f"text_preview='{self.text[:30]}...')>"
        )

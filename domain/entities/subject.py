"""
Subject Domain Value Object

Учебный предмет (дисциплина).
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Subject:
    """
    Value Object для предмета

    Предметы неизменяемы.
    """

    # Identity
    id: Optional[int]
    name: str

    def __post_init__(self):
        """Валидация"""
        if not self.name or len(self.name.strip()) == 0:
            raise ValueError("Subject name cannot be empty")

        if len(self.name) > 255:
            raise ValueError("Subject name too long (max 255 chars)")

    def __repr__(self):
        return f"<Subject(id={self.id}, name={self.name})>"

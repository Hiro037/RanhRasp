"""
Classroom Value Object

Номер аудитории.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Classroom:
    """
    Value Object для аудитории

    Неизменяемый объект.
    """

    number: str

    def __post_init__(self):
        """Валидация"""
        if not self.number or len(self.number.strip()) == 0:
            # Аудитория может быть не указана
            object.__setattr__(self, 'number', "Не указана")

        if len(self.number) > 50:
            raise ValueError("Classroom number too long (max 50 chars)")

    def is_specified(self) -> bool:
        """Указана ли аудитория"""
        return self.number != "Не указана"

    def __repr__(self):
        return f"<Classroom({self.number})>"

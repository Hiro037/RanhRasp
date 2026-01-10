"""
TimeSlot Value Object

Временной слот для занятия.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TimeSlot:
    """
    Value Object для временного слота

    Неизменяемый объект с валидацией.
    """

    start: datetime
    end: datetime

    def __post_init__(self):
        """Валидация"""
        if not self.is_valid():
            raise ValueError("Invalid time slot: end must be after start")

    def is_valid(self) -> bool:
        """Валидный ли временной слот"""
        return self.end > self.start

    def duration_minutes(self) -> int:
        """Длительность в минутах"""
        delta = self.end - self.start
        return int(delta.total_seconds() / 60)

    def contains(self, time: datetime) -> bool:
        """Находится ли время внутри слота"""
        return self.start <= time <= self.end

    def overlaps(self, other: 'TimeSlot') -> bool:
        """Пересекается ли с другим временным слотом"""
        return (
                self.start < other.end and
                other.start < self.end
        )

    def __repr__(self):
        return f"<TimeSlot({self.start.strftime('%H:%M')} - {self.end.strftime('%H:%M')})>"

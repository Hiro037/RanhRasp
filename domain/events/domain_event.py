"""
Base Domain Event

Базовый класс для всех доменных событий.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import uuid4


@dataclass(frozen=True, kw_only=True)  # frozen=True делает immutable
class DomainEvent:
    """
    Базовый класс для доменных событий

    Все события наследуются от него.
    События неизменяемы после создания.
    """

    # Уникальный ID события
    event_id: str = field(default_factory=lambda: str(uuid4()))

    # Временная метка события
    timestamp: datetime = field(default_factory=datetime.now)

    # Версия события (для эволюции схемы)
    event_version: int = 1

    # Опциональные метаданные
    correlation_id: Optional[str] = None  # Для трейсинга запросов
    causation_id: Optional[str] = None  # ID события-причины

    def __post_init__(self):
        """Валидация базовых полей"""
        if not self.event_id:
            raise ValueError("event_id cannot be empty")

        if not self.timestamp:
            raise ValueError("timestamp cannot be empty")

    @property
    def event_name(self) -> str:
        """
        Название события (имя класса)

        Returns:
            Имя класса события
        """
        return self.__class__.__name__

    def to_dict(self) -> dict:
        """
        Преобразовать событие в словарь

        Полезно для сериализации в JSON/MessageQueue.

        Returns:
            Словарь с данными события
        """
        return {
            "event_id": self.event_id,
            "event_name": self.event_name,
            "event_version": self.event_version,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
        }

    def __repr__(self):
        return (
            f"<{self.event_name}(event_id={self.event_id}, "
            f"timestamp={self.timestamp.isoformat()})>"
        )

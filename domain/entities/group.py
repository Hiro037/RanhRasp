"""
Group Domain Entity

Учебная группа.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Group:
    """
    Entity для учебной группы
    """

    # Identity
    id: Optional[int]  # None для новых групп
    name: str

    def __post_init__(self):
        """Валидация после создания"""
        self._validate()

    def _validate(self):
        """Валидация бизнес-правил"""
        if not self.name or len(self.name.strip()) == 0:
            raise ValueError("Group name cannot be empty")

        if len(self.name) > 50:
            raise ValueError("Group name too long (max 50 chars)")

    def __repr__(self):
        return f"<Group(id={self.id}, name={self.name})>"

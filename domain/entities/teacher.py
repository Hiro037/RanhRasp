"""
Teacher Domain Entity

Представляет преподавателя.
"""

from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class Teacher:
    """
    Teacher Entity

    Содержит информацию о преподавателе и связь с User.
    """

    # Identity
    id: Optional[int]  # None для новых преподавателей
    name: str

    # Contact info (optional)
    email: Optional[str] = None
    phone: Optional[str] = None

    # Relationship to User (ID, не объект!)
    user_account_id: Optional[int] = None

    # Domain events
    _events: List = field(default_factory=list, repr=False)

    def __post_init__(self):
        """Валидация после создания"""
        self._validate()

    def _validate(self):
        """Валидация бизнес-правил"""
        if not self.name or len(self.name.strip()) == 0:
            raise ValueError("Teacher name cannot be empty")

        if len(self.name) > 255:
            raise ValueError("Teacher name too long (max 255 chars)")

        if self.email and "@" not in self.email:
            raise ValueError("Invalid email format")

    # ========== BUSINESS LOGIC ==========

    def has_user_account(self) -> bool:
        """Есть ли у преподавателя аккаунт в Telegram"""
        return self.user_account_id is not None

    def link_user_account(self, user_account_id: int) -> None:
        """
        Связать преподавателя с аккаунтом пользователя

        Args:
            user_account_id: ID пользователя

        Raises:
            ValueError: если аккаунт уже привязан
        """
        if self.has_user_account():
            raise ValueError("Teacher already has a linked user account")

        if user_account_id <= 0:
            raise ValueError("Invalid user_account_id")

        self.user_account_id = user_account_id

    def update_contact_info(
            self,
            email: Optional[str] = None,
            phone: Optional[str] = None
    ) -> None:
        """Обновить контактную информацию"""
        if email is not None:
            if "@" not in email:
                raise ValueError("Invalid email format")
            self.email = email

        if phone is not None:
            self.phone = phone

    # ========== DOMAIN EVENTS ==========

    def get_uncommitted_events(self) -> List:
        """Получить и очистить неопубликованные события"""
        events = self._events.copy()
        self._events.clear()
        return events

    def __repr__(self):
        return f"<Teacher(id={self.id}, name={self.name})>"

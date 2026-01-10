"""
User Repository Interface

Интерфейс для работы с пользователями.
"""

from abc import abstractmethod
from typing import Optional, List
from datetime import datetime

from domain.repositories.base_repository import IBaseRepository
from domain.entities.user import User, UserType


class IUserRepository(IBaseRepository[User]):
    """
    Интерфейс репозитория пользователей

    Определяет операции для работы с User entities.
    """

    # ========== СПЕЦИФИЧНЫЕ МЕТОДЫ ==========

    @abstractmethod
    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        """
        Получить пользователя по Telegram ID

        Args:
            telegram_id: Telegram user ID

        Returns:
            Пользователь или None
        """
        pass

    @abstractmethod
    async def get_by_username(self, username: str) -> Optional[User]:
        """
        Получить пользователя по username

        Args:
            username: Telegram username

        Returns:
            Пользователь или None
        """
        pass

    @abstractmethod
    async def get_by_type(
            self,
            user_type: UserType,
            limit: Optional[int] = None,
            offset: Optional[int] = None
    ) -> List[User]:
        """
        Получить всех пользователей определенного типа

        Args:
            user_type: Тип пользователя (student/teacher)
            limit: Максимальное количество
            offset: Смещение

        Returns:
            Список пользователей
        """
        pass

    @abstractmethod
    async def get_by_group(
            self,
            group_id: int,
            limit: Optional[int] = None,
            offset: Optional[int] = None
    ) -> List[User]:
        """
        Получить всех студентов группы

        Args:
            group_id: ID группы
            limit: Максимальное количество
            offset: Смещение

        Returns:
            Список студентов группы
        """
        pass

    @abstractmethod
    async def get_verified_teachers(
            self,
            limit: Optional[int] = None,
            offset: Optional[int] = None
    ) -> List[User]:
        """
        Получить всех верифицированных преподавателей

        Args:
            limit: Максимальное количество
            offset: Смещение

        Returns:
            Список верифицированных преподавателей
        """
        pass

    @abstractmethod
    async def get_active_users(
            self,
            since: datetime,
            limit: Optional[int] = None,
            offset: Optional[int] = None
    ) -> List[User]:
        """
        Получить активных пользователей с определенной даты

        Args:
            since: Дата начала активности
            limit: Максимальное количество
            offset: Смещение

        Returns:
            Список активных пользователей
        """
        pass

    @abstractmethod
    async def count_by_type(self, user_type: UserType) -> int:
        """
        Подсчитать количество пользователей по типу

        Args:
            user_type: Тип пользователя

        Returns:
            Количество пользователей данного типа
        """
        pass

    @abstractmethod
    async def exists_by_telegram_id(self, telegram_id: int) -> bool:
        """
        Проверить существование пользователя по Telegram ID

        Args:
            telegram_id: Telegram user ID

        Returns:
            True если существует
        """
        pass

    @abstractmethod
    async def update_activity(self, user_id: int) -> None:
        """
        Обновить время последней активности пользователя

        Args:
            user_id: ID пользователя (внутренний)
        """
        pass

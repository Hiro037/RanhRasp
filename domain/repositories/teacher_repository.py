"""
Teacher Repository Interface

Интерфейс для работы с преподавателями.
"""

from abc import abstractmethod
from typing import Optional, List

from domain.repositories.base_repository import IBaseRepository
from domain.entities.teacher import Teacher


class ITeacherRepository(IBaseRepository[Teacher]):
    """
    Интерфейс репозитория преподавателей

    Определяет операции для работы с Teacher entities.
    """

    # ========== СПЕЦИФИЧНЫЕ МЕТОДЫ ==========

    @abstractmethod
    async def get_by_name(self, name: str) -> Optional[Teacher]:
        """
        Получить преподавателя по имени

        Args:
            name: ФИО преподавателя

        Returns:
            Преподаватель или None
        """
        pass

    @abstractmethod
    async def get_by_user_account_id(self, user_account_id: int) -> Optional[Teacher]:
        """
        Получить преподавателя по ID связанного пользователя

        Args:
            user_account_id: ID пользователя (User.id)

        Returns:
            Преподаватель или None
        """
        pass

    @abstractmethod
    async def search_by_name(
            self,
            query: str,
            limit: Optional[int] = None,
            offset: Optional[int] = None
    ) -> List[Teacher]:
        """
        Поиск преподавателей по имени (частичное совпадение)

        Args:
            query: Поисковый запрос
            limit: Максимальное количество
            offset: Смещение

        Returns:
            Список преподавателей
        """
        pass

    @abstractmethod
    async def get_teachers_with_accounts(
            self,
            limit: Optional[int] = None,
            offset: Optional[int] = None
    ) -> List[Teacher]:
        """
        Получить преподавателей с привязанными аккаунтами

        Args:
            limit: Максимальное количество
            offset: Смещение

        Returns:
            Список преподавателей с аккаунтами
        """
        pass

    @abstractmethod
    async def get_teachers_without_accounts(
            self,
            limit: Optional[int] = None,
            offset: Optional[int] = None
    ) -> List[Teacher]:
        """
        Получить преподавателей без привязанных аккаунтов

        Args:
            limit: Максимальное количество
            offset: Смещение

        Returns:
            Список преподавателей без аккаунтов
        """
        pass

    @abstractmethod
    async def exists_by_name(self, name: str) -> bool:
        """
        Проверить существование преподавателя по имени

        Args:
            name: ФИО преподавателя

        Returns:
            True если существует
        """
        pass

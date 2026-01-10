"""
Base Repository Interface

Базовый интерфейс для всех репозиториев.
Определяет общие CRUD операции.
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Optional, List

# Generic type для entity
T = TypeVar('T')


class IBaseRepository(ABC, Generic[T]):
    """
    Базовый интерфейс репозитория

    Определяет стандартные CRUD операции.
    Все репозитории наследуются от него.
    """

    @abstractmethod
    async def get_by_id(self, entity_id: int) -> Optional[T]:
        """
        Получить сущность по ID

        Args:
            entity_id: ID сущности

        Returns:
            Сущность или None если не найдена
        """
        pass

    @abstractmethod
    async def get_all(
            self,
            limit: Optional[int] = None,
            offset: Optional[int] = None
    ) -> List[T]:
        """
        Получить все сущности

        Args:
            limit: Максимальное количество записей
            offset: Смещение для пагинации

        Returns:
            Список сущностей
        """
        pass

    @abstractmethod
    async def add(self, entity: T) -> T:
        """
        Добавить новую сущность

        Args:
            entity: Сущность для добавления

        Returns:
            Сущность с заполненным ID
        """
        pass

    @abstractmethod
    async def update(self, entity: T) -> T:
        """
        Обновить существующую сущность

        Args:
            entity: Сущность с изменениями

        Returns:
            Обновленная сущность
        """
        pass

    @abstractmethod
    async def delete(self, entity_id: int) -> bool:
        """
        Удалить сущность по ID

        Args:
            entity_id: ID сущности

        Returns:
            True если удалена, False если не найдена
        """
        pass

    @abstractmethod
    async def exists(self, entity_id: int) -> bool:
        """
        Проверить существование сущности

        Args:
            entity_id: ID сущности

        Returns:
            True если существует, False иначе
        """
        pass

    @abstractmethod
    async def count(self) -> int:
        """
        Получить общее количество сущностей

        Returns:
            Количество записей
        """
        pass

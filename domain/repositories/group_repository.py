"""
Group Repository Interface

Интерфейс для работы с группами.
"""

from abc import abstractmethod
from typing import Optional, List

from domain.repositories.base_repository import IBaseRepository
from domain.entities.group import Group


class IGroupRepository(IBaseRepository[Group]):
    """
    Интерфейс репозитория групп

    Определяет операции для работы с Group entities.
    """

    # ========== СПЕЦИФИЧНЫЕ МЕТОДЫ ==========

    @abstractmethod
    async def get_by_name(self, name: str) -> Optional[Group]:
        """
        Получить группу по названию

        Args:
            name: Название группы (например, "ЭК-101")

        Returns:
            Группа или None
        """
        pass

    @abstractmethod
    async def search_by_name(
            self,
            query: str,
            limit: Optional[int] = None,
            offset: Optional[int] = None
    ) -> List[Group]:
        """
        Поиск групп по названию (частичное совпадение)

        Args:
            query: Поисковый запрос
            limit: Максимальное количество
            offset: Смещение

        Returns:
            Список групп
        """
        pass

    @abstractmethod
    async def get_all_sorted(self) -> List[Group]:
        """
        Получить все группы, отсортированные по названию

        Returns:
            Список групп
        """
        pass

    @abstractmethod
    async def exists_by_name(self, name: str) -> bool:
        """
        Проверить существование группы по названию

        Args:
            name: Название группы

        Returns:
            True если существует
        """
        pass

    @abstractmethod
    async def count_students(self, group_id: int) -> int:
        """
        Подсчитать количество студентов в группе

        Args:
            group_id: ID группы

        Returns:
            Количество студентов
        """
        pass

"""
Subject Repository Interface

Интерфейс для работы с предметами.
"""

from abc import abstractmethod
from typing import Optional, List

from domain.repositories.base_repository import IBaseRepository
from domain.entities.subject import Subject


class ISubjectRepository(IBaseRepository[Subject]):
    """
    Интерфейс репозитория предметов

    Определяет операции для работы с Subject entities.
    """

    # ========== СПЕЦИФИЧНЫЕ МЕТОДЫ ==========

    @abstractmethod
    async def get_by_name(self, name: str) -> Optional[Subject]:
        """
        Получить предмет по названию

        Args:
            name: Название предмета

        Returns:
            Предмет или None
        """
        pass

    @abstractmethod
    async def search_by_name(
            self,
            query: str,
            limit: Optional[int] = None,
            offset: Optional[int] = None
    ) -> List[Subject]:
        """
        Поиск предметов по названию (частичное совпадение)

        Args:
            query: Поисковый запрос
            limit: Максимальное количество
            offset: Смещение

        Returns:
            Список предметов
        """
        pass

    @abstractmethod
    async def get_by_teacher(
            self,
            teacher_id: int,
            limit: Optional[int] = None,
            offset: Optional[int] = None
    ) -> List[Subject]:
        """
        Получить предметы, которые ведет преподаватель

        Args:
            teacher_id: ID преподавателя
            limit: Максимальное количество
            offset: Смещение

        Returns:
            Список предметов
        """
        pass

    @abstractmethod
    async def get_by_group(
            self,
            group_id: int,
            limit: Optional[int] = None,
            offset: Optional[int] = None
    ) -> List[Subject]:
        """
        Получить предметы, которые изучает группа

        Args:
            group_id: ID группы
            limit: Максимальное количество
            offset: Смещение

        Returns:
            Список предметов
        """
        pass

    @abstractmethod
    async def exists_by_name(self, name: str) -> bool:
        """
        Проверить существование предмета по названию

        Args:
            name: Название предмета

        Returns:
            True если существует
        """
        pass

    @abstractmethod
    async def get_all_sorted(self) -> List[Subject]:
        """
        Получить все предметы, отсортированные по названию

        Returns:
            Список предметов
        """
        pass

"""
Lesson Repository Interface

Интерфейс для работы с занятиями.
"""

from abc import abstractmethod
from typing import Optional, List
from datetime import datetime, date

from domain.repositories.base_repository import IBaseRepository
from domain.entities.lesson import Lesson


class ILessonRepository(IBaseRepository[Lesson]):
    """
    Интерфейс репозитория занятий

    Определяет операции для работы с Lesson entities.
    """

    # ========== СПЕЦИФИЧНЫЕ МЕТОДЫ ==========

    @abstractmethod
    async def get_by_group(
            self,
            group_id: int,
            start_date: Optional[date] = None,
            end_date: Optional[date] = None,
            limit: Optional[int] = None,
            offset: Optional[int] = None
    ) -> List[Lesson]:
        """
        Получить занятия группы

        Args:
            group_id: ID группы
            start_date: Начальная дата (опционально)
            end_date: Конечная дата (опционально)
            limit: Максимальное количество
            offset: Смещение

        Returns:
            Список занятий группы
        """
        pass

    @abstractmethod
    async def get_by_teacher(
            self,
            teacher_id: int,
            start_date: Optional[date] = None,
            end_date: Optional[date] = None,
            limit: Optional[int] = None,
            offset: Optional[int] = None
    ) -> List[Lesson]:
        """
        Получить занятия преподавателя

        Args:
            teacher_id: ID преподавателя
            start_date: Начальная дата (опционально)
            end_date: Конечная дата (опционально)
            limit: Максимальное количество
            offset: Смещение

        Returns:
            Список занятий преподавателя
        """
        pass

    @abstractmethod
    async def get_by_date_range(
            self,
            start_date: date,
            end_date: date,
            group_id: Optional[int] = None,
            teacher_id: Optional[int] = None,
            limit: Optional[int] = None,
            offset: Optional[int] = None
    ) -> List[Lesson]:
        """
        Получить занятия за период

        Args:
            start_date: Начальная дата
            end_date: Конечная дата
            group_id: Фильтр по группе (опционально)
            teacher_id: Фильтр по преподавателю (опционально)
            limit: Максимальное количество
            offset: Смещение

        Returns:
            Список занятий за период
        """
        pass

    @abstractmethod
    async def get_by_date(
            self,
            target_date: date,
            group_id: Optional[int] = None,
            teacher_id: Optional[int] = None
    ) -> List[Lesson]:
        """
        Получить занятия на конкретную дату

        Args:
            target_date: Целевая дата
            group_id: Фильтр по группе (опционально)
            teacher_id: Фильтр по преподавателю (опционально)

        Returns:
            Список занятий на дату
        """
        pass

    @abstractmethod
    async def get_upcoming(
            self,
            current_time: datetime,
            group_id: Optional[int] = None,
            teacher_id: Optional[int] = None,
            limit: Optional[int] = None
    ) -> List[Lesson]:
        """
        Получить предстоящие занятия

        Args:
            current_time: Текущее время
            group_id: Фильтр по группе (опционально)
            teacher_id: Фильтр по преподавателю (опционально)
            limit: Максимальное количество

        Returns:
            Список предстоящих занятий
        """
        pass

    @abstractmethod
    async def get_in_progress(
            self,
            current_time: datetime,
            group_id: Optional[int] = None,
            teacher_id: Optional[int] = None
    ) -> List[Lesson]:
        """
        Получить занятия, которые идут сейчас

        Args:
            current_time: Текущее время
            group_id: Фильтр по группе (опционально)
            teacher_id: Фильтр по преподавателю (опционально)

        Returns:
            Список текущих занятий
        """
        pass

    @abstractmethod
    async def get_with_comments(
            self,
            group_id: Optional[int] = None,
            start_date: Optional[date] = None,
            limit: Optional[int] = None,
            offset: Optional[int] = None
    ) -> List[Lesson]:
        """
        Получить занятия с комментариями

        Args:
            group_id: Фильтр по группе (опционально)
            start_date: Начальная дата (опционально)
            limit: Максимальное количество
            offset: Смещение

        Returns:
            Список занятий с комментариями
        """
        pass

    @abstractmethod
    async def save(self, lesson: Lesson) -> Lesson:
        """
        Сохранить занятие (с комментариями!)

        Специальный метод для сохранения aggregate root
        со всеми связанными сущностями (комментариями).

        Args:
            lesson: Занятие для сохранения

        Returns:
            Сохраненное занятие с заполненными ID
        """
        pass

    @abstractmethod
    async def count_by_group(self, group_id: int) -> int:
        """
        Подсчитать количество занятий группы

        Args:
            group_id: ID группы

        Returns:
            Количество занятий
        """
        pass

    @abstractmethod
    async def count_by_teacher(self, teacher_id: int) -> int:
        """
        Подсчитать количество занятий преподавателя

        Args:
            teacher_id: ID преподавателя

        Returns:
            Количество занятий
        """
        pass

"""
Schedule Validation Service

Domain Service для валидации расписания с учетом совмещенных занятий.
"""

from typing import Optional, List, Set
from datetime import datetime

from domain.entities.lesson import Lesson


class ScheduleValidationService:
    """
    Domain Service для валидации расписания

    Содержит бизнес-правила валидации, которые затрагивают
    несколько Lesson entities.
    """

    def check_schedule_conflicts(
            self,
            new_lesson: Lesson,
            existing_lessons: List[Lesson]
    ) -> Optional[Lesson]:
        """
        Проверить конфликты в расписании

        Конфликт возникает если:
        1. Пересечение по времени
        2. И (конфликт аудитории ИЛИ конфликт преподавателя ИЛИ конфликт группы)

        Args:
            new_lesson: Новое занятие для проверки
            existing_lessons: Существующие занятия

        Returns:
            Конфликтующее занятие или None
        """
        for existing in existing_lessons:
            # Пропускаем само себя (если обновление)
            if new_lesson.id and new_lesson.id == existing.id:
                continue

            # Проверяем пересечение времени
            if not new_lesson.time_slot.overlaps(existing.time_slot):
                continue

            # Проверяем различные типы конфликтов
            if self._has_conflict(new_lesson, existing):
                return existing

        return None

    def _has_conflict(self, lesson1: Lesson, lesson2: Lesson) -> bool:
        """
        Проверить наличие конфликта между двумя занятиями

        Args:
            lesson1: Первое занятие
            lesson2: Второе занятие

        Returns:
            True если есть конфликт
        """
        # Конфликт аудитории
        if lesson1.classroom == lesson2.classroom:
            return True

        # Конфликт преподавателя
        if lesson1.teacher_id == lesson2.teacher_id:
            return True

        # Конфликт группы (пересечение множеств)
        if self._has_group_conflict(lesson1, lesson2):
            return True

        return False

    def _has_group_conflict(self, lesson1: Lesson, lesson2: Lesson) -> bool:
        """
        Проверить конфликт по группам

        Конфликт есть если у занятий есть общие группы.

        Args:
            lesson1: Первое занятие
            lesson2: Второе занятие

        Returns:
            True если есть общие группы
        """
        set1: Set[int] = set(lesson1.group_ids)
        set2: Set[int] = set(lesson2.group_ids)

        # Пересечение множеств
        common_groups = set1 & set2

        return len(common_groups) > 0

    def validate_lesson_duration(self, lesson: Lesson) -> bool:
        """
        Валидация длительности занятия (бизнес-правило)

        Бизнес-правило: занятие должно быть от 45 до 240 минут

        Args:
            lesson: Занятие для валидации

        Returns:
            True если длительность валидна
        """
        duration = lesson.time_slot.duration_minutes()

        # Минимум 45 минут (академический час)
        # Максимум 240 минут (4 академических часа)
        return 45 <= duration <= 240

    def validate_classroom_capacity(
            self,
            lesson: Lesson,
            group_sizes: dict[int, int],
            classroom_capacity: int
    ) -> bool:
        """
        Валидация вместимости аудитории (бизнес-правило)

        Args:
            lesson: Занятие
            group_sizes: Словарь {group_id: количество студентов}
            classroom_capacity: Вместимость аудитории

        Returns:
            True если аудитория вмещает всех студентов
        """
        total_students = sum(
            group_sizes.get(group_id, 0)
            for group_id in lesson.group_ids
        )

        return total_students <= classroom_capacity

    def can_combine_lessons(self, lesson1: Lesson, lesson2: Lesson) -> bool:
        """
        Проверить, можно ли объединить два занятия в совмещенное

        Условия объединения:
        - Одинаковое время
        - Одинаковый преподаватель
        - Одинаковый предмет
        - Одинаковая аудитория
        - Разные группы (нет пересечения)

        Args:
            lesson1: Первое занятие
            lesson2: Второе занятие

        Returns:
            True если можно объединить
        """
        # Проверка времени (строгое равенство)
        if lesson1.time_slot != lesson2.time_slot:
            return False

        # Проверка преподавателя
        if lesson1.teacher_id != lesson2.teacher_id:
            return False

        # Проверка предмета
        if lesson1.subject_id != lesson2.subject_id:
            return False

        # Проверка аудитории
        if lesson1.classroom != lesson2.classroom:
            return False

        # Проверка, что группы не пересекаются
        if self._has_group_conflict(lesson1, lesson2):
            return False

        return True

    def suggest_alternative_time(
            self,
            conflicting_lesson: Lesson,
            existing_lessons: List[Lesson],
            search_range_hours: int = 8
    ) -> Optional[datetime]:
        """
        Предложить альтернативное время для занятия

        Ищет свободный слот в пределах search_range_hours часов
        от оригинального времени.

        Args:
            conflicting_lesson: Занятие с конфликтом
            existing_lessons: Существующие занятия
            search_range_hours: Диапазон поиска в часах

        Returns:
            Альтернативное время начала или None
        """
        from datetime import timedelta

        original_start = conflicting_lesson.time_slot.start
        duration = conflicting_lesson.time_slot.duration_minutes()

        # Проверяем слоты с шагом 15 минут
        for offset_minutes in range(0, search_range_hours * 60, 15):
            if offset_minutes == 0:
                continue  # Пропускаем оригинальное время

            # Пробуем вперед
            new_start = original_start + timedelta(minutes=offset_minutes)
            if self._is_time_slot_free(
                    new_start,
                    duration,
                    conflicting_lesson,
                    existing_lessons
            ):
                return new_start

            # Пробуем назад
            new_start = original_start - timedelta(minutes=offset_minutes)
            if self._is_time_slot_free(
                    new_start,
                    duration,
                    conflicting_lesson,
                    existing_lessons
            ):
                return new_start

        return None

    def _is_time_slot_free(
            self,
            start: datetime,
            duration_minutes: int,
            lesson: Lesson,
            existing_lessons: List[Lesson]
    ) -> bool:
        """
        Проверить, свободен ли временной слот

        Args:
            start: Начало слота
            duration_minutes: Длительность
            lesson: Занятие для проверки
            existing_lessons: Существующие занятия

        Returns:
            True если слот свободен
        """
        from datetime import timedelta
        from domain.value_objects.time_slot import TimeSlot

        end = start + timedelta(minutes=duration_minutes)
        test_time_slot = TimeSlot(start=start, end=end)

        # Создаем тестовое занятие
        test_lesson = Lesson(
            id=None,
            time_slot=test_time_slot,
            classroom=lesson.classroom,
            teacher_id=lesson.teacher_id,
            subject_id=lesson.subject_id,
            group_ids=lesson.group_ids.copy()
        )

        # Проверяем конфликты
        conflict = self.check_schedule_conflicts(test_lesson, existing_lessons)

        return conflict is None

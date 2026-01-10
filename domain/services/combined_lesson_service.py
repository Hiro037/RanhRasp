"""
Combined Lesson Service

Domain Service для работы с совмещенными занятиями.
"""

from typing import List, Optional, Dict, Set
from datetime import datetime

from domain.entities.lesson import Lesson


class CombinedLessonService:
    """
    Domain Service для управления совмещенными занятиями

    Содержит бизнес-логику объединения и разделения занятий.
    """

    def find_combinable_lessons(
            self,
            lessons: List[Lesson]
    ) -> List[List[Lesson]]:
        """
        Найти группы занятий, которые можно объединить

        Возвращает список групп, где каждая группа - это занятия,
        которые можно объединить в одно совмещенное.

        Args:
            lessons: Список занятий для анализа

        Returns:
            Список групп занятий для объединения
            Пример: [[lesson1, lesson2], [lesson3, lesson4, lesson5]]
        """
        from domain.services.schedule_validation_service import ScheduleValidationService

        validator = ScheduleValidationService()

        # Группируем по ключу (время, преподаватель, предмет, аудитория)
        groups: Dict[tuple, List[Lesson]] = {}

        for lesson in lessons:
            key = self._get_lesson_key(lesson)

            if key not in groups:
                groups[key] = []

            groups[key].append(lesson)

        # Фильтруем группы с 2+ занятиями и без конфликтов групп
        result = []
        for group in groups.values():
            if len(group) >= 2:
                # Проверяем, что группы не пересекаются
                if self._groups_are_distinct(group):
                    result.append(group)

        return result

    def _get_lesson_key(self, lesson: Lesson) -> tuple:
        """
        Получить ключ для группировки занятий

        Args:
            lesson: Занятие

        Returns:
            Кортеж (время_начала, время_конца, преподаватель, предмет, аудитория)
        """
        return (
            lesson.time_slot.start,
            lesson.time_slot.end,
            lesson.teacher_id,
            lesson.subject_id,
            lesson.classroom.number
        )

    def _groups_are_distinct(self, lessons: List[Lesson]) -> bool:
        """
        Проверить, что у занятий нет общих групп

        Args:
            lessons: Список занятий

        Returns:
            True если группы не пересекаются
        """
        all_groups: Set[int] = set()

        for lesson in lessons:
            lesson_groups = set(lesson.group_ids)

            # Проверяем пересечение
            if all_groups & lesson_groups:
                return False

            all_groups.update(lesson_groups)

        return True

    def merge_lessons(self, lessons: List[Lesson]) -> Lesson:
        """
        Объединить несколько занятий в одно совмещенное

        Создает новое занятие с объединенными group_ids.

        Args:
            lessons: Занятия для объединения (должны быть combinable)

        Returns:
            Новое совмещенное занятие

        Raises:
            ValueError: если занятия нельзя объединить
        """
        if len(lessons) < 2:
            raise ValueError("Need at least 2 lessons to merge")

        # Проверяем, что можно объединить
        from domain.services.schedule_validation_service import ScheduleValidationService
        validator = ScheduleValidationService()

        base_lesson = lessons[0]
        for other_lesson in lessons[1:]:
            if not validator.can_combine_lessons(base_lesson, other_lesson):
                raise ValueError(
                    f"Cannot combine lessons {base_lesson.id} and {other_lesson.id}"
                )

        # Собираем все group_ids
        all_group_ids: Set[int] = set()
        for lesson in lessons:
            all_group_ids.update(lesson.group_ids)

        # Создаем новое совмещенное занятие
        merged_lesson = Lesson(
            id=base_lesson.id,  # Используем ID первого занятия
            time_slot=base_lesson.time_slot,
            classroom=base_lesson.classroom,
            teacher_id=base_lesson.teacher_id,
            subject_id=base_lesson.subject_id,
            lesson_type=base_lesson.lesson_type,
            group_ids=sorted(list(all_group_ids)),  # Объединенные группы
            comments=base_lesson.comments.copy()  # Комментарии первого занятия
        )

        return merged_lesson

    def split_lesson(
            self,
            lesson: Lesson,
            group_ids_to_split: List[int]
    ) -> tuple[Lesson, Lesson]:
        """
        Разделить совмещенное занятие на два

        Args:
            lesson: Совмещенное занятие для разделения
            group_ids_to_split: Группы для выделения в отдельное занятие

        Returns:
            Кортеж (оставшееся занятие, новое отдельное занятие)

        Raises:
            ValueError: если нельзя разделить
        """
        if not lesson.is_combined_lesson():
            raise ValueError("Cannot split non-combined lesson")

        if not group_ids_to_split:
            raise ValueError("No groups specified for splitting")

        # Проверяем, что все указанные группы есть в занятии
        for group_id in group_ids_to_split:
            if not lesson.has_group(group_id):
                raise ValueError(f"Group {group_id} not found in lesson")

        # Вычисляем оставшиеся группы
        remaining_group_ids = [
            gid for gid in lesson.group_ids
            if gid not in group_ids_to_split
        ]

        if not remaining_group_ids:
            raise ValueError("Cannot split all groups from lesson")

        # Создаем оставшееся занятие (модифицированное оригинальное)
        remaining_lesson = Lesson(
            id=lesson.id,
            time_slot=lesson.time_slot,
            classroom=lesson.classroom,
            teacher_id=lesson.teacher_id,
            subject_id=lesson.subject_id,
            lesson_type=lesson.lesson_type,
            group_ids=remaining_group_ids,
            comments=lesson.comments.copy()
        )

        # Создаем новое отдельное занятие
        new_lesson = Lesson(
            id=None,  # Новое занятие получит ID при сохранении
            time_slot=lesson.time_slot,
            classroom=lesson.classroom,
            teacher_id=lesson.teacher_id,
            subject_id=lesson.subject_id,
            lesson_type=lesson.lesson_type,
            group_ids=group_ids_to_split,
            comments=[]  # Комментарии остаются у оригинального
        )

        return remaining_lesson, new_lesson

    def calculate_combined_lesson_stats(
            self,
            lessons: List[Lesson]
    ) -> Dict[str, any]:
        """
        Рассчитать статистику по совмещенным занятиям

        Args:
            lessons: Список всех занятий

        Returns:
            Словарь со статистикой:
            - total_lessons: общее количество занятий
            - combined_lessons: количество совмещенных
            - total_groups: всего групп в совмещенных занятиях
            - max_groups_per_lesson: максимум групп в одном занятии
        """
        combined = [l for l in lessons if l.is_combined_lesson()]

        if not combined:
            return {
                "total_lessons": len(lessons),
                "combined_lessons": 0,
                "total_groups": 0,
                "max_groups_per_lesson": 0,
                "average_groups_per_combined": 0.0
            }

        total_groups = sum(len(l.group_ids) for l in combined)
        max_groups = max(len(l.group_ids) for l in combined)
        avg_groups = total_groups / len(combined)

        return {
            "total_lessons": len(lessons),
            "combined_lessons": len(combined),
            "total_groups": total_groups,
            "max_groups_per_lesson": max_groups,
            "average_groups_per_combined": round(avg_groups, 2)
        }

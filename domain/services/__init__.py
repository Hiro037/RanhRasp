"""
Domain Services Public API

Экспортируем domain services для использования в application layer.
"""

from domain.services.schedule_validation_service import ScheduleValidationService
from domain.services.combined_lesson_service import CombinedLessonService

__all__ = [
    "ScheduleValidationService",
    "CombinedLessonService",
]

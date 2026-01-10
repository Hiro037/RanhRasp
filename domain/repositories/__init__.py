"""
Domain Repositories Public API

Экспортируем все интерфейсы репозиториев.
"""

from domain.repositories.base_repository import IBaseRepository
from domain.repositories.user_repository import IUserRepository
from domain.repositories.teacher_repository import ITeacherRepository
from domain.repositories.lesson_repository import ILessonRepository
from domain.repositories.group_repository import IGroupRepository
from domain.repositories.subject_repository import ISubjectRepository

__all__ = [
    "IBaseRepository",
    "IUserRepository",
    "ITeacherRepository",
    "ILessonRepository",
    "IGroupRepository",
    "ISubjectRepository",
]

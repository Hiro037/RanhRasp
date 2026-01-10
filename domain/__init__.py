"""
Domain Layer Public API

Экспортируем только то, что должно использоваться другими слоями.
"""

# Entities
from domain.entities.user import User, UserType
from domain.entities.teacher import Teacher
from domain.entities.lesson import Lesson
from domain.entities.comment import Comment
from domain.entities.group import Group
from domain.entities.subject import Subject

# Value Objects
from domain.value_objects.time_slot import TimeSlot
from domain.value_objects.classroom import Classroom

__all__ = [
    # Entities
    "User",
    "UserType",
    "Teacher",
    "Lesson",
    "Comment",
    "Group",
    "Subject",

    # Value Objects
    "TimeSlot",
    "Classroom",
]

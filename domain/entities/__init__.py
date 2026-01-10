'''
Domain Entities Public API

Все абстрактные сущности.
'''

from domain.entities.user import User
from domain.entities.subject import Subject
from domain.entities.group import Group
from domain.entities.teacher import Teacher
from domain.entities.comment import Comment
from domain.entities.lesson import Lesson


__all__ = [
    "User",
    "Subject",
    "Group",
    "Teacher",
    "Comment",
    "Lesson",
]
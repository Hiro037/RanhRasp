"""
Domain Events Public API

Экспортируем все события.
Используется в application/infrastructure слоях.
"""

# Base event
from domain.events.domain_event import DomainEvent

# User events
from domain.events.user_events import (
    UserCreatedEvent,
    UserVerifiedEvent,
    UserGroupChangedEvent,
    UserActivityRecordedEvent,
)

# Comment events
from domain.events.comment_events import (
    CommentAddedEvent,
    CommentUpdatedEvent,
    CommentDeletedEvent,
)

# Lesson events
from domain.events.lesson_events import (
    LessonCreatedEvent,
    LessonUpdatedEvent,
    LessonCancelledEvent,
    LessonStartedEvent,
    LessonEndedEvent,
)

# Teacher events
from domain.events.teacher_events import (
    TeacherRegisteredEvent,
    TeacherLinkedToUserEvent,
    TeacherVerifiedEvent,
    TeacherContactInfoUpdatedEvent,
)

__all__ = [
    # Base
    "DomainEvent",

    # User events
    "UserCreatedEvent",
    "UserVerifiedEvent",
    "UserGroupChangedEvent",
    "UserActivityRecordedEvent",

    # Comment events
    "CommentAddedEvent",
    "CommentUpdatedEvent",
    "CommentDeletedEvent",

    # Lesson events
    "LessonCreatedEvent",
    "LessonUpdatedEvent",
    "LessonCancelledEvent",
    "LessonStartedEvent",
    "LessonEndedEvent",

    # Teacher events
    "TeacherRegisteredEvent",
    "TeacherLinkedToUserEvent",
    "TeacherVerifiedEvent",
    "TeacherContactInfoUpdatedEvent",
]

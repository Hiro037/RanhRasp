"""
Core business logic: users, schedule, comments, CRUD, logs, caching.
All functions use async sessions and Redis.
"""

from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple, Callable, Awaitable
from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from core.models import (
    Base, User, Teacher, Group, Subject, Classroom, Lesson, LessonGroup, GroupUser,
    Platform, ScheduleMessageType, LessonType, LogStatus, TZ, get_current_time, Log
)
from core.database import AsyncSessionLocal
from core.redis_client import get_cache, set_cache, get_binary_cache, set_binary_cache, delete_cache
from core.utils import get_current_date, get_current_datetime
import json

# ---------- User management ----------
async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()

async def get_user_by_platform_id(db: AsyncSession, platform: Platform, platform_id: int) -> Optional[User]:
    if platform == Platform.TELEGRAM:
        stmt = select(User).where(User.tg_id == platform_id)
    else:
        stmt = select(User).where(User.vk_id == platform_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def create_user(db: AsyncSession, platform: Platform, platform_id: int, name: str) -> User:
    user = User(
        tg_id=platform_id if platform == Platform.TELEGRAM else None,
        vk_id=platform_id if platform == Platform.VK else None,
        name=name,
        is_admin=False,
        is_notification_on=True,
        schedule_message_type=ScheduleMessageType.TEXT
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

async def get_or_create_user(db: AsyncSession, platform: Platform, platform_id: int, name: str) -> User:
    user = await get_user_by_platform_id(db, platform, platform_id)
    if not user:
        user = await create_user(db, platform, platform_id, name)
    else:
        # update last_activity and name
        user.last_activity = get_current_time()
        if user.name != name:
            user.name = name
        await db.commit()
        await db.refresh(user)
    # eager load groups for later use
    await db.refresh(user, attribute_names=["groups"])
    return user

async def set_student_group(db: AsyncSession, user_id: int, group_id: int) -> bool:
    user = await db.get(User, user_id)
    if not user:
        return False
    # clear any teacher role
    user.teacher_profile_id = None
    # remove old group links
    await db.execute(delete(GroupUser).where(GroupUser.user_id == user_id))
    # add new group
    db.add(GroupUser(user_id=user_id, group_id=group_id))
    await db.commit()
    return True

async def remove_student_group(db: AsyncSession, user_id: int) -> bool:
    await db.execute(delete(GroupUser).where(GroupUser.user_id == user_id))
    await db.commit()
    return True

async def request_teacher_role(db: AsyncSession, user_id: int) -> bool:
    # remove any group links, set teacher_profile_id = NULL
    user = await db.get(User, user_id)
    if not user:
        return False
    await db.execute(delete(GroupUser).where(GroupUser.user_id == user_id))
    user.teacher_profile_id = None
    await db.commit()
    return True

async def get_pending_teacher_requests(db: AsyncSession) -> List[User]:
    # users with no teacher_profile_id and no groups
    subq = select(GroupUser.user_id).subquery()
    stmt = select(User).where(
        User.teacher_profile_id.is_(None),
        User.id.not_in(subq)
    )
    result = await db.execute(stmt)
    return result.scalars().all()

async def approve_teacher_request(db: AsyncSession, admin_user_id: int, target_user_id: int, teacher_id: int) -> bool:
    admin = await db.get(User, admin_user_id)
    if not admin or not admin.is_admin:
        return False
    target = await db.get(User, target_user_id)
    if not target:
        return False
    target.teacher_profile_id = teacher_id
    await db.commit()
    return True

async def reject_teacher_request(db: AsyncSession, admin_user_id: int, target_user_id: int) -> bool:
    admin = await db.get(User, admin_user_id)
    if not admin or not admin.is_admin:
        return False
    target = await db.get(User, target_user_id)
    if not target:
        return False
    # remove any group links and teacher_profile
    await db.execute(delete(GroupUser).where(GroupUser.user_id == target_user_id))
    target.teacher_profile_id = None
    await db.commit()
    return True

async def update_notification_setting(db: AsyncSession, user_id: int, enabled: bool) -> None:
    user = await db.get(User, user_id)
    if user:
        user.is_notification_on = enabled
        await db.commit()

async def update_schedule_message_type(db: AsyncSession, user_id: int, msg_type: ScheduleMessageType) -> None:
    user = await db.get(User, user_id)
    if user:
        user.schedule_message_type = msg_type
        await db.commit()

def get_user_role(user: User) -> str:
    if user.is_admin:
        return "admin"
    if user.teacher_profile_id is not None:
        return "teacher"
    return "student"

# ---------- Schedule fetching ----------
async def get_lessons_for_user(db: AsyncSession, user_id: int, start_date: date, end_date: date) -> List[Lesson]:
    user = await db.get(User, user_id)
    if not user:
        return []
    role = get_user_role(user)
    start_dt = datetime.combine(start_date, datetime.min.time()).astimezone(TZ)
    end_dt = datetime.combine(end_date, datetime.max.time()).astimezone(TZ)
    if role == "student":
        # get groups
        await db.refresh(user, attribute_names=["groups"])
        group_ids = [g.id for g in user.groups]
        if not group_ids:
            return []
        stmt = (
            select(Lesson)
            .join(LessonGroup)
            .where(
                LessonGroup.group_id.in_(group_ids),
                Lesson.start_datetime >= start_dt,
                Lesson.start_datetime <= end_dt
            )
            .order_by(Lesson.start_datetime)
            .options(
                selectinload(Lesson.subject),
                selectinload(Lesson.teacher),
                selectinload(Lesson.classroom),
                selectinload(Lesson.groups)
            )
        )
        result = await db.execute(stmt)
        return result.unique().scalars().all()
    elif role == "teacher":
        stmt = (
            select(Lesson)
            .where(
                Lesson.teacher_id == user.teacher_profile_id,
                Lesson.start_datetime >= start_dt,
                Lesson.start_datetime <= end_dt
            )
            .order_by(Lesson.start_datetime)
            .options(
                selectinload(Lesson.subject),
                selectinload(Lesson.teacher),
                selectinload(Lesson.classroom),
                selectinload(Lesson.groups)
            )
        )
        result = await db.execute(stmt)
        return result.scalars().all()
    else:  # admin
        stmt = (
            select(Lesson)
            .where(
                Lesson.start_datetime >= start_dt,
                Lesson.start_datetime <= end_dt
            )
            .order_by(Lesson.start_datetime)
            .options(
                selectinload(Lesson.subject),
                selectinload(Lesson.teacher),
                selectinload(Lesson.classroom),
                selectinload(Lesson.groups)
            )
        )
        result = await db.execute(stmt)
        return result.scalars().all()

async def get_lessons_for_group(db: AsyncSession, group_id: int, start_date: date, end_date: date) -> List[Lesson]:
    start_dt = datetime.combine(start_date, datetime.min.time()).astimezone(TZ)
    end_dt = datetime.combine(end_date, datetime.max.time()).astimezone(TZ)
    stmt = (
        select(Lesson)
        .join(LessonGroup)
        .where(
            LessonGroup.group_id == group_id,
            Lesson.start_datetime >= start_dt,
            Lesson.start_datetime <= end_dt
        )
        .order_by(Lesson.start_datetime)
        .options(
            selectinload(Lesson.subject),
            selectinload(Lesson.teacher),
            selectinload(Lesson.classroom)
        )
    )
    result = await db.execute(stmt)
    return result.unique().scalars().all()

async def get_group_by_user_id(db: AsyncSession, user_id: int) -> Optional[Group]:
    user = await db.get(User, user_id)
    if user and user.groups:
        return user.groups[0]
    return None

# ---------- Formatting ----------
def format_lesson_time(lesson: Lesson) -> str:
    start = lesson.start_datetime.astimezone(TZ)
    end = lesson.end_datetime.astimezone(TZ)
    return f"{start.strftime('%H:%M')}–{end.strftime('%H:%M')}"

def format_lesson_short(lesson: Lesson) -> str:
    subject = lesson.subject.name if lesson.subject else "—"
    teacher = lesson.teacher.name if lesson.teacher else "—"
    room = lesson.classroom.name if lesson.classroom else "—"
    comment = f" ({lesson.comment})" if lesson.comment else ""
    return f"{format_lesson_time(lesson)} | {subject} | {teacher} | ауд.{room}{comment}"

def format_schedule_text(lessons: List[Lesson], target_date: date) -> str:
    if not lessons:
        return f"📭 Нет занятий на {target_date.strftime('%d.%m.%Y')}."
    lines = [f"📅 *{target_date.strftime('%d.%m.%Y')}*"]
    for i, lesson in enumerate(lessons, 1):
        lines.append(f"{i}. {format_lesson_short(lesson)}")
    return "\n".join(lines)

# ---------- Cached schedule ----------
async def get_schedule_text_cached(user_id: int, target_date: date) -> str:
    cache_key = f"schedule_text:{user_id}:{target_date.isoformat()}"
    cached = await get_cache(cache_key)
    if cached:
        return cached
    async with AsyncSessionLocal() as db:
        lessons = await get_lessons_for_user(db, user_id, target_date, target_date)
        text = format_schedule_text(lessons, target_date)
        await set_cache(cache_key, text, ttl=3600)
        return text

async def get_schedule_image_cached(user_id: int, target_date: date) -> Optional[bytes]:
    cache_key = f"schedule_img:{user_id}:{target_date.isoformat()}"
    cached = await get_binary_cache(cache_key)
    if cached:
        return cached
    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_id)
        if not user:
            return None
        role = get_user_role(user)
        if role == "student":
            group = await get_group_by_user_id(db, user_id)
            if not group:
                return None
            lessons = await get_lessons_for_group(db, group.id, target_date, target_date)
        elif role == "teacher":
            # teacher: show all groups they teach? For simplicity, show first group
            # better: show all lessons of that teacher (groups will be displayed)
            lessons = await get_lessons_for_user(db, user_id, target_date, target_date)
            # For image we need a group name – we can pick a placeholder
            group_name = "Преподаватель"
        else:
            # admin: for now text only
            return None
        # Prepare data for jinja renderer
        from core.jinja_renderer import render_html, html_to_image
        lessons_data = []
        for lesson in lessons:
            # get group names for this lesson (first group)
            group_names = [g.name for g in lesson.groups] if lesson.groups else ["—"]
            group_display = ", ".join(group_names)
            lessons_data.append({
                "start_time": format_lesson_time(lesson),
                "subject": lesson.subject.name if lesson.subject else "—",
                "teacher": lesson.teacher.name if lesson.teacher else "—",
                "type": lesson.type.value.upper(),
                "classroom": lesson.classroom.name if lesson.classroom else "—",
                "comment": lesson.comment or "",
                "groups": group_display
            })
        if role == "student":
            html = await render_html(target_date, group.name, lessons_data)
        else:
            html = await render_html(target_date, "Расписание преподавателя", lessons_data)
        img_bytes = await html_to_image(html)
        await set_binary_cache(cache_key, img_bytes, ttl=3600)
        return img_bytes

# ---------- Teacher comment ----------
async def add_comment_to_lesson(db: AsyncSession, lesson_id: int, teacher_user_id: int, comment: str) -> Tuple[bool, str]:
    teacher = await db.get(User, teacher_user_id)
    if not teacher or teacher.teacher_profile_id is None:
        return False, "Только преподаватели могут добавлять комментарии."
    lesson = await db.get(Lesson, lesson_id)
    if not lesson:
        return False, "Занятие не найдено."
    if lesson.teacher_id != teacher.teacher_profile_id:
        return False, "Вы можете комментировать только свои занятия."
    lesson.comment = comment
    await db.commit()
    return True, "Комментарий добавлен."

# ---------- CRUD for groups, teachers, subjects, classrooms (admin only) ----------
def _check_admin(db: AsyncSession, user_id: int) -> bool:
    # helper, but we will check inside each function
    pass

async def create_group(db: AsyncSession, admin_user_id: int, name: str) -> Optional[Group]:
    admin = await db.get(User, admin_user_id)
    if not admin or not admin.is_admin:
        return None
    group = Group(name=name)
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return group

async def get_group_by_id(db: AsyncSession, group_id: int) -> Optional[Group]:
    return await db.get(Group, group_id)

async def get_all_groups(db: AsyncSession) -> List[Group]:
    result = await db.execute(select(Group).order_by(Group.name))
    return result.scalars().all()

async def update_group(db: AsyncSession, admin_user_id: int, group_id: int, name: str) -> bool:
    admin = await db.get(User, admin_user_id)
    if not admin or not admin.is_admin:
        return False
    group = await db.get(Group, group_id)
    if not group:
        return False
    group.name = name
    await db.commit()
    return True

async def delete_group(db: AsyncSession, admin_user_id: int, group_id: int) -> bool:
    admin = await db.get(User, admin_user_id)
    if not admin or not admin.is_admin:
        return False
    group = await db.get(Group, group_id)
    if not group:
        return False
    await db.delete(group)
    await db.commit()
    return True

# Teachers (entity)
async def create_teacher(db: AsyncSession, admin_user_id: int, name: str) -> Optional[Teacher]:
    admin = await db.get(User, admin_user_id)
    if not admin or not admin.is_admin:
        return None
    teacher = Teacher(name=name)
    db.add(teacher)
    await db.commit()
    await db.refresh(teacher)
    return teacher

async def get_all_teachers(db: AsyncSession) -> List[Teacher]:
    result = await db.execute(select(Teacher).order_by(Teacher.name))
    return result.scalars().all()

async def get_teacher_by_id(db: AsyncSession, teacher_id: int) -> Optional[Teacher]:
    return await db.get(Teacher, teacher_id)

async def update_teacher(db: AsyncSession, admin_user_id: int, teacher_id: int, name: str) -> bool:
    admin = await db.get(User, admin_user_id)
    if not admin or not admin.is_admin:
        return False
    teacher = await db.get(Teacher, teacher_id)
    if not teacher:
        return False
    teacher.name = name
    await db.commit()
    return True

async def delete_teacher(db: AsyncSession, admin_user_id: int, teacher_id: int) -> bool:
    admin = await db.get(User, admin_user_id)
    if not admin or not admin.is_admin:
        return False
    teacher = await db.get(Teacher, teacher_id)
    if not teacher:
        return False
    await db.delete(teacher)
    await db.commit()
    return True

# Subjects
async def create_subject(db: AsyncSession, admin_user_id: int, name: str) -> Optional[Subject]:
    admin = await db.get(User, admin_user_id)
    if not admin or not admin.is_admin:
        return None
    subject = Subject(name=name)
    db.add(subject)
    await db.commit()
    await db.refresh(subject)
    return subject

async def get_all_subjects(db: AsyncSession) -> List[Subject]:
    result = await db.execute(select(Subject).order_by(Subject.name))
    return result.scalars().all()

async def get_subject_by_id(db: AsyncSession, subject_id: int) -> Optional[Subject]:
    return await db.get(Subject, subject_id)

async def update_subject(db: AsyncSession, admin_user_id: int, subject_id: int, name: str) -> bool:
    admin = await db.get(User, admin_user_id)
    if not admin or not admin.is_admin:
        return False
    subject = await db.get(Subject, subject_id)
    if not subject:
        return False
    subject.name = name
    await db.commit()
    return True

async def delete_subject(db: AsyncSession, admin_user_id: int, subject_id: int) -> bool:
    admin = await db.get(User, admin_user_id)
    if not admin or not admin.is_admin:
        return False
    subject = await db.get(Subject, subject_id)
    if not subject:
        return False
    await db.delete(subject)
    await db.commit()
    return True

# Classrooms
async def create_classroom(db: AsyncSession, admin_user_id: int, name: str) -> Optional[Classroom]:
    admin = await db.get(User, admin_user_id)
    if not admin or not admin.is_admin:
        return None
    classroom = Classroom(name=name)
    db.add(classroom)
    await db.commit()
    await db.refresh(classroom)
    return classroom

async def get_all_classrooms(db: AsyncSession) -> List[Classroom]:
    result = await db.execute(select(Classroom).order_by(Classroom.name))
    return result.scalars().all()

async def get_classroom_by_id(db: AsyncSession, classroom_id: int) -> Optional[Classroom]:
    return await db.get(Classroom, classroom_id)

async def update_classroom(db: AsyncSession, admin_user_id: int, classroom_id: int, name: str) -> bool:
    admin = await db.get(User, admin_user_id)
    if not admin or not admin.is_admin:
        return False
    classroom = await db.get(Classroom, classroom_id)
    if not classroom:
        return False
    classroom.name = name
    await db.commit()
    return True

async def delete_classroom(db: AsyncSession, admin_user_id: int, classroom_id: int) -> bool:
    admin = await db.get(User, admin_user_id)
    if not admin or not admin.is_admin:
        return False
    classroom = await db.get(Classroom, classroom_id)
    if not classroom:
        return False
    await db.delete(classroom)
    await db.commit()
    return True

# Lessons CRUD
async def create_lesson(db: AsyncSession, admin_user_id: int, data: dict) -> Optional[Lesson]:
    admin = await db.get(User, admin_user_id)
    if not admin or not admin.is_admin:
        return None
    lesson = Lesson(
        start_datetime=data["start_datetime"],
        end_datetime=data["end_datetime"],
        type=data["type"],
        classroom_id=data.get("classroom_id"),
        teacher_id=data.get("teacher_id"),
        subject_id=data.get("subject_id"),
        comment=data.get("comment", "")
    )
    db.add(lesson)
    await db.commit()
    await db.refresh(lesson)
    # add group links
    group_ids = data.get("group_ids", [])
    for gid in group_ids:
        db.add(LessonGroup(lesson_id=lesson.id, group_id=gid))
    await db.commit()
    return lesson

async def get_lesson_by_id(db: AsyncSession, lesson_id: int) -> Optional[Lesson]:
    return await db.get(Lesson, lesson_id)

async def get_lessons_by_date(db: AsyncSession, target_date: date) -> List[Lesson]:
    start_dt = datetime.combine(target_date, datetime.min.time()).astimezone(TZ)
    end_dt = datetime.combine(target_date, datetime.max.time()).astimezone(TZ)
    stmt = select(Lesson).where(
        Lesson.start_datetime >= start_dt,
        Lesson.start_datetime <= end_dt
    ).order_by(Lesson.start_datetime)
    result = await db.execute(stmt)
    return result.scalars().all()

async def update_lesson(db: AsyncSession, admin_user_id: int, lesson_id: int, data: dict) -> bool:
    admin = await db.get(User, admin_user_id)
    if not admin or not admin.is_admin:
        return False
    lesson = await db.get(Lesson, lesson_id)
    if not lesson:
        return False
    # update fields
    for field in ["start_datetime", "end_datetime", "type", "classroom_id", "teacher_id", "subject_id", "comment"]:
        if field in data:
            setattr(lesson, field, data[field])
    await db.commit()
    # update group links if provided
    if "group_ids" in data:
        await db.execute(delete(LessonGroup).where(LessonGroup.lesson_id == lesson_id))
        for gid in data["group_ids"]:
            db.add(LessonGroup(lesson_id=lesson_id, group_id=gid))
        await db.commit()
    return True

async def delete_lesson(db: AsyncSession, admin_user_id: int, lesson_id: int) -> bool:
    admin = await db.get(User, admin_user_id)
    if not admin or not admin.is_admin:
        return False
    lesson = await db.get(Lesson, lesson_id)
    if not lesson:
        return False
    await db.delete(lesson)
    await db.commit()
    return True

# ---------- Logging ----------
async def log_action(db: AsyncSession, user_id: Optional[int], platform: Platform,
                      action_type: str, status: LogStatus, details: dict = None) -> None:
    log = Log(
        user_id=user_id,
        platform=platform,
        action_type=action_type,
        status=status,
        details=details
    )
    db.add(log)
    await db.commit()

# ---------- Users with notifications enabled ----------
async def get_all_users_with_notifications(db: AsyncSession) -> List[User]:
    """
    Return all users who have is_notification_on = True.
    Used by notifier to send daily updates.
    """
    stmt = select(User).where(User.is_notification_on == True)
    result = await db.execute(stmt)
    return result.scalars().all()
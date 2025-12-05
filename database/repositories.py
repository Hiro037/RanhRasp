"""
Data Access Layer (Репозитории) для работы с БД

Изолирует бизнес-логику от деталей работы с БД
"""
from datetime import datetime, date, timedelta
from typing import Optional, List, Sequence

from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import User, UserRequest, Group, Teacher, Subject, Lesson


# ========== USER REPOSITORY ==========

class UserRepository:
    """Репозиторий для работы с пользователями"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_telegram_id(self, user_id: int) -> Optional[User]:
        """Получить пользователя по Telegram ID"""
        result = await self.session.execute(
            select(User)
            .where(User.user_id == user_id)
            .options(selectinload(User.group))
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, id: int) -> Optional[User]:
        """Получить пользователя по внутреннему ID"""
        result = await self.session.execute(
            select(User)
            .where(User.id == id)
            .options(selectinload(User.group))
        )
        return result.scalar_one_or_none()

    async def create(
            self,
            user_id: int,
            username: Optional[str] = None,
            group_id: Optional[int] = None
    ) -> User:
        """Создать нового пользователя"""
        user = User(
            user_id=user_id,
            username=username,
            group_id=group_id,
            created_at=datetime.now(),
            last_activity=datetime.now(),
            total_requests=0
        )
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def get_or_create(
            self,
            user_id: int,
            username: Optional[str] = None
    ) -> tuple[User, bool]:
        """
        Получить существующего или создать нового пользователя

        Returns:
            tuple[User, bool]: (пользователь, был_ли_создан)
        """
        user = await self.get_by_telegram_id(user_id)
        if user:
            # Обновляем username если изменился
            if username and user.username != username:
                user.username = username
                await self.session.flush()
            return user, False

        user = await self.create(user_id, username)
        return user, True

    async def update_group(self, user_id: int, group_id: Optional[int]) -> Optional[User]:
        """Обновить группу пользователя"""
        user = await self.get_by_telegram_id(user_id)
        if user:
            user.group_id = group_id
            await self.session.flush()
            await self.session.refresh(user)
        return user

    async def update_activity(self, user_id: int) -> None:
        """Обновить время последней активности"""
        await self.session.execute(
            update(User)
            .where(User.user_id == user_id)
            .values(
                last_activity=datetime.now(),
                total_requests=User.total_requests + 1
            )
        )

    async def get_all(self, limit: int = 100, offset: int = 0) -> Sequence[User]:
        """Получить всех пользователей с пагинацией"""
        result = await self.session.execute(
            select(User)
            .options(selectinload(User.group))
            .order_by(User.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def get_by_group(self, group_id: int) -> Sequence[User]:
        """Получить всех пользователей группы"""
        result = await self.session.execute(
            select(User)
            .where(User.group_id == group_id)
            .options(selectinload(User.group))
            .order_by(User.username)
        )
        return result.scalars().all()

    async def count_total(self) -> int:
        """Получить общее количество пользователей"""
        result = await self.session.execute(
            select(func.count()).select_from(User)
        )
        return result.scalar_one()

    async def count_active(self, days: int = 7) -> int:
        """Получить количество активных пользователей за последние N дней"""
        threshold = datetime.now() - timedelta(days=days)
        result = await self.session.execute(
            select(func.count())
            .select_from(User)
            .where(User.last_activity >= threshold)
        )
        return result.scalar_one()


# ========== USER REQUEST REPOSITORY ==========

class UserRequestRepository:
    """Репозиторий для работы с запросами пользователей"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
            self,
            user_id: int,  # внутренний ID User
            request_type: str,
            request_data: Optional[str] = None,
            group_snapshot: Optional[str] = None,
            telegram_id: Optional[int] = None,
            username: Optional[str] = None,
    ) -> UserRequest:
        """Создать запись о запросе пользователя"""
        request = UserRequest(
            user_id=user_id,
            request_type=request_type,
            request_data=request_data,
            group_snapshot=group_snapshot,
            telegram_id=telegram_id,
            username=username,
            timestamp=datetime.now()
        )
        self.session.add(request)
        await self.session.flush()
        return request

    async def get_user_requests(
            self,
            user_id: int,
            limit: int = 50
    ) -> Sequence[UserRequest]:
        """Получить последние запросы пользователя"""
        result = await self.session.execute(
            select(UserRequest)
            .where(UserRequest.user_id == user_id)
            .order_by(UserRequest.timestamp.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def get_by_type(
            self,
            request_type: str,
            days: int = 7
    ) -> Sequence[UserRequest]:
        """Получить запросы определенного типа за последние N дней"""
        threshold = datetime.now() - timedelta(days=days)
        result = await self.session.execute(
            select(UserRequest)
            .where(
                and_(
                    UserRequest.request_type == request_type,
                    UserRequest.timestamp >= threshold
                )
            )
            .order_by(UserRequest.timestamp.desc())
        )
        return result.scalars().all()

    async def count_by_type(self, days: int = 7) -> List[tuple[str, int]]:
        """Получить статистику по типам запросов"""
        threshold = datetime.now() - timedelta(days=days)
        result = await self.session.execute(
            select(
                UserRequest.request_type,
                func.count(UserRequest.id).label('count')
            )
            .where(UserRequest.timestamp >= threshold)
            .group_by(UserRequest.request_type)
            .order_by(func.count(UserRequest.id).desc())
        )
        return result.all()


# ========== GROUP REPOSITORY ==========

class GroupRepository:
    """Репозиторий для работы с группами"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, group_id: int) -> Optional[Group]:
        """Получить группу по ID"""
        result = await self.session.execute(
            select(Group)
            .where(Group.group_id == group_id)
            .options(selectinload(Group.students))
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, group_name: str) -> Optional[Group]:
        """Получить группу по имени"""
        result = await self.session.execute(
            select(Group)
            .where(Group.group_name == group_name)
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> Sequence[Group]:
        """Получить все группы"""
        result = await self.session.execute(
            select(Group).order_by(Group.group_name)
        )
        return result.scalars().all()

    async def create(self, group_name: str) -> Group:
        """Создать новую группу"""
        group = Group(group_name=group_name)
        self.session.add(group)
        await self.session.flush()
        await self.session.refresh(group)
        return group

    async def update(self, group_id: int, group_name: str) -> Optional[Group]:
        """Обновить группу"""
        group = await self.get_by_id(group_id)
        if group:
            group.group_name = group_name
            await self.session.flush()
            await self.session.refresh(group)
        return group

    async def delete(self, group_id: int) -> bool:
        """Удалить группу"""
        result = await self.session.execute(
            delete(Group).where(Group.group_id == group_id)
        )
        return result.rowcount > 0


# ========== LESSON REPOSITORY ==========

class LessonRepository:
    """Репозиторий для работы с занятиями"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, lesson_id: int) -> Optional[Lesson]:
        """Получить занятие по ID"""
        result = await self.session.execute(
            select(Lesson)
            .where(Lesson.lesson_id == lesson_id)
            .options(
                selectinload(Lesson.group),
                selectinload(Lesson.teacher),
                selectinload(Lesson.subject)
            )
        )
        return result.scalar_one_or_none()

    async def get_by_group_and_date(
            self,
            group_id: int,
            target_date: date
    ) -> Sequence[Lesson]:
        """Получить занятия группы на конкретную дату"""
        start_datetime = datetime.combine(target_date, datetime.min.time())
        end_datetime = datetime.combine(target_date, datetime.max.time())

        result = await self.session.execute(
            select(Lesson)
            .where(
                and_(
                    Lesson.group_id == group_id,
                    Lesson.start_datetime >= start_datetime,
                    Lesson.start_datetime <= end_datetime
                )
            )
            .options(
                selectinload(Lesson.teacher),
                selectinload(Lesson.subject),
                selectinload(Lesson.group)
            )
            .order_by(Lesson.start_datetime)
        )
        return result.scalars().all()

    async def get_by_group_and_range(
            self,
            group_id: int,
            start_date: date,
            end_date: date
    ) -> Sequence[Lesson]:
        """Получить занятия группы за период"""
        start_datetime = datetime.combine(start_date, datetime.min.time())
        end_datetime = datetime.combine(end_date, datetime.max.time())

        result = await self.session.execute(
            select(Lesson)
            .where(
                and_(
                    Lesson.group_id == group_id,
                    Lesson.start_datetime >= start_datetime,
                    Lesson.start_datetime <= end_datetime
                )
            )
            .options(
                selectinload(Lesson.teacher),
                selectinload(Lesson.subject),
                selectinload(Lesson.group)
            )
            .order_by(Lesson.start_datetime)
        )
        return result.scalars().all()

    async def create(
            self,
            start_datetime: datetime,
            end_datetime: datetime,
            group_id: int,
            teacher_id: int,
            subject_id: int,
            classroom: str,
            lesson_type: Optional[str] = None
    ) -> Lesson:
        """Создать новое занятие"""
        lesson = Lesson(
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            group_id=group_id,
            teacher_id=teacher_id,
            subject_id=subject_id,
            classroom=classroom,
            lesson_type=lesson_type
        )
        self.session.add(lesson)
        await self.session.flush()
        await self.session.refresh(lesson)
        return lesson

    async def delete_by_group_and_range(
            self,
            group_id: int,
            start_date: date,
            end_date: date
    ) -> int:
        """Удалить занятия группы за период (для обновления расписания)"""
        start_datetime = datetime.combine(start_date, datetime.min.time())
        end_datetime = datetime.combine(end_date, datetime.max.time())

        result = await self.session.execute(
            delete(Lesson)
            .where(
                and_(
                    Lesson.group_id == group_id,
                    Lesson.start_datetime >= start_datetime,
                    Lesson.start_datetime <= end_datetime
                )
            )
        )
        return result.rowcount


# ========== TEACHER REPOSITORY ==========

class TeacherRepository:
    """Репозиторий для работы с преподавателями"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, teacher_id: int) -> Optional[Teacher]:
        """Получить преподавателя по ID"""
        result = await self.session.execute(
            select(Teacher).where(Teacher.teacher_id == teacher_id)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[Teacher]:
        """Получить преподавателя по имени"""
        result = await self.session.execute(
            select(Teacher).where(Teacher.name == name)
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> Sequence[Teacher]:
        """Получить всех преподавателей"""
        result = await self.session.execute(
            select(Teacher).order_by(Teacher.name)
        )
        return result.scalars().all()

    async def create(
            self,
            name: str,
            email: Optional[str] = None,
            phone: Optional[str] = None
    ) -> Teacher:
        """Создать нового преподавателя"""
        teacher = Teacher(name=name, email=email, phone=phone)
        self.session.add(teacher)
        await self.session.flush()
        await self.session.refresh(teacher)
        return teacher

    async def get_or_create(self, name: str) -> tuple[Teacher, bool]:
        """Получить существующего или создать нового преподавателя"""
        teacher = await self.get_by_name(name)
        if teacher:
            return teacher, False
        teacher = await self.create(name)
        return teacher, True


# ========== SUBJECT REPOSITORY ==========

class SubjectRepository:
    """Репозиторий для работы с предметами"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, subject_id: int) -> Optional[Subject]:
        """Получить предмет по ID"""
        result = await self.session.execute(
            select(Subject).where(Subject.subject_id == subject_id)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[Subject]:
        """Получить предмет по названию"""
        result = await self.session.execute(
            select(Subject).where(Subject.name == name)
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> Sequence[Subject]:
        """Получить все предметы"""
        result = await self.session.execute(
            select(Subject).order_by(Subject.name)
        )
        return result.scalars().all()

    async def create(self, name: str) -> Subject:
        """Создать новый предмет"""
        subject = Subject(name=name)
        self.session.add(subject)
        await self.session.flush()
        await self.session.refresh(subject)
        return subject

    async def get_or_create(self, name: str) -> tuple[Subject, bool]:
        """Получить существующий или создать новый предмет"""
        subject = await self.get_by_name(name)
        if subject:
            return subject, False
        subject = await self.create(name)
        return subject, True


# ========== UNIT OF WORK PATTERN ==========

class UnitOfWork:
    """
    Unit of Work паттерн для управления транзакциями

    Использование:
    async with UnitOfWork() as uow:
        user = await uow.users.get_by_telegram_id(123456)
        await uow.user_requests.create(user.id, "command", "/start")
        await uow.commit()
    """

    def __init__(self):
        self.session: Optional[AsyncSession] = None

    async def __aenter__(self):
        from database.models import async_session_maker
        self.session = async_session_maker()

        # Создаем репозитории
        self.users = UserRepository(self.session)
        self.user_requests = UserRequestRepository(self.session)
        self.groups = GroupRepository(self.session)
        self.lessons = LessonRepository(self.session)
        self.teachers = TeacherRepository(self.session)
        self.subjects = SubjectRepository(self.session)

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            await self.rollback()
        await self.session.close()

    async def commit(self):
        """Зафиксировать изменения"""
        await self.session.commit()

    async def rollback(self):
        """Откатить изменения"""
        await self.session.rollback()

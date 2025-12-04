"""
Скрипт миграции данных из синхронной БД в асинхронную

ИСПОЛЬЗОВАНИЕ:
python migration_sync_to_async.py
"""
import asyncio
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Старая синхронная схема
from create_database import Base as OldBase, Group as OldGroup, Teacher as OldTeacher, \
    Subject as OldSubject, Lesson as OldLesson, engine as old_engine

# Новая асинхронная схема
from database.models import init_db
from database.repositories import UnitOfWork


async def migrate_data():
    """Миграция данных из старой БД в новую"""
    print("🚀 Начало миграции данных...")

    # Инициализируем новую БД
    print("📦 Инициализация новой БД...")
    await init_db()

    # Создаем старую синхронную сессию
    OldSession = sessionmaker(bind=old_engine)
    old_session = OldSession()

    try:
        # Миграция групп
        print("\n📚 Миграция групп...")
        old_groups = old_session.query(OldGroup).all()
        group_mapping = {}  # старый ID -> новый ID

        async with UnitOfWork() as uow:
            for old_group in old_groups:
                new_group = await uow.groups.create(old_group.group_name)
                group_mapping[old_group.group_id] = new_group.group_id
                print(f"  ✓ {old_group.group_name}")
            await uow.commit()

        print(f"✅ Мигрировано групп: {len(old_groups)}")

        # Миграция преподавателей
        print("\n👨‍🏫 Миграция преподавателей...")
        old_teachers = old_session.query(OldTeacher).all()
        teacher_mapping = {}

        async with UnitOfWork() as uow:
            for old_teacher in old_teachers:
                new_teacher = await uow.teachers.create(old_teacher.name)
                teacher_mapping[old_teacher.teacher_id] = new_teacher.teacher_id
                print(f"  ✓ {old_teacher.name}")
            await uow.commit()

        print(f"✅ Мигрировано преподавателей: {len(old_teachers)}")

        # Миграция предметов
        print("\n📖 Миграция предметов...")
        old_subjects = old_session.query(OldSubject).all()
        subject_mapping = {}

        async with UnitOfWork() as uow:
            for old_subject in old_subjects:
                new_subject = await uow.subjects.create(old_subject.name)
                subject_mapping[old_subject.subject_id] = new_subject.subject_id
                print(f"  ✓ {old_subject.name}")
            await uow.commit()

        print(f"✅ Мигрировано предметов: {len(old_subjects)}")

        # Миграция занятий
        print("\n📅 Миграция занятий...")
        old_lessons = old_session.query(OldLesson).all()

        async with UnitOfWork() as uow:
            for i, old_lesson in enumerate(old_lessons, 1):
                await uow.lessons.create(
                    start_datetime=old_lesson.start_datetime,
                    end_datetime=old_lesson.end_datetime,
                    group_id=group_mapping[old_lesson.group_id],
                    teacher_id=teacher_mapping[old_lesson.teacher_id],
                    subject_id=subject_mapping[old_lesson.subject_id],
                    classroom=old_lesson.classroom,
                    lesson_type=old_lesson.lesson_type
                )

                if i % 100 == 0:
                    print(f"  Обработано: {i}/{len(old_lessons)}")

            await uow.commit()

        print(f"✅ Мигрировано занятий: {len(old_lessons)}")

        print("\n🎉 Миграция успешно завершена!")
        print(f"📊 Статистика:")
        print(f"   - Групп: {len(old_groups)}")
        print(f"   - Преподавателей: {len(old_teachers)}")
        print(f"   - Предметов: {len(old_subjects)}")
        print(f"   - Занятий: {len(old_lessons)}")

    except Exception as e:
        print(f"\n❌ Ошибка миграции: {e}")
        import traceback
        traceback.print_exc()
    finally:
        old_session.close()


if __name__ == "__main__":
    asyncio.run(migrate_data())

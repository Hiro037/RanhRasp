"""
Асинхронное FastAPI приложение для управления расписанием RanhRasp

Основные возможности:
- CRUD операции для всех сущностей (группы, преподаватели, предметы, занятия, пользователи)
- Загрузка расписания из файлов
- REST API эндпоинты
- Админ-панель через HTML шаблоны
- Полная асинхронность с использованием UnitOfWork паттерна
"""
import os
from datetime import datetime, timedelta, date
from typing import Optional, List
from pathlib import Path

from fastapi import FastAPI, Request, Form, HTTPException, UploadFile, File, Query, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database.models import User, Group, Teacher, Subject, Lesson, get_session
from database.repositories import UnitOfWork
from test_parse import (
    parse_docx_schedule,
    import_schedule_to_db_async,
    convert_doc_to_docx,
    validate_schedule_file,
    print_schedule_summary
)

# ========== ИНИЦИАЛИЗАЦИЯ ПРИЛОЖЕНИЯ ==========

app = FastAPI(
    title="RanhRasp API",
    description="API для управления расписанием учебных занятий",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене указать конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Шаблоны
templates = Jinja2Templates(directory="templates")

# Статические файлы
os.makedirs("files", exist_ok=True)
os.makedirs("static", exist_ok=True)
app.mount("/files", StaticFiles(directory="files"), name="files")

# Если есть папка static с CSS/JS
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

def format_datetime(dt: datetime) -> str:
    """Форматирование datetime для шаблонов"""
    return dt.strftime("%d.%m.%Y %H:%M")


def format_date(d: date) -> str:
    """Форматирование date для шаблонов"""
    return d.strftime("%d.%m.%Y")


# Добавляем функции в контекст шаблонов
templates.env.globals.update({
    'format_datetime': format_datetime,
    'format_date': format_date
})


# ========== ГЛАВНАЯ СТРАНИЦА ==========

@app.get("/", response_class=HTMLResponse, tags=["Web UI"])
async def index(request: Request):
    """
    Главная страница с обзором всех сущностей

    Показывает:
    - Список групп
    - Список преподавателей
    - Список предметов
    - Последние занятия (100 шт)
    """
    async with UnitOfWork() as uow:
        groups = await uow.groups.get_all()
        teachers = await uow.teachers.get_all()
        subjects = await uow.subjects.get_all()

        # Получаем последние 100 занятий
        result = await uow.session.execute(
            select(Lesson)
            .options(
                selectinload(Lesson.group),
                selectinload(Lesson.teacher),
                selectinload(Lesson.subject)
            )
            .order_by(Lesson.start_datetime.desc())
            .limit(100)
        )
        lessons = result.scalars().all()

        # Статистика пользователей
        total_users = await uow.users.count_total()
        active_users = await uow.users.count_active(days=7)

    return templates.TemplateResponse("index.html", {
        "request": request,
        "groups": groups,
        "teachers": teachers,
        "subjects": subjects,
        "lessons": lessons,
        "total_users": total_users,
        "active_users": active_users
    })


# ========== API ЭНДПОИНТЫ - ИНФОРМАЦИЯ ==========

@app.get("/api/health", tags=["System"])
async def health_check():
    """Проверка здоровья API"""
    return {
        "status": "ok",
        "version": "2.0.0",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/stats", tags=["Statistics"])
async def get_statistics():
    """Получить статистику системы"""
    async with UnitOfWork() as uow:
        stats = {
            "users": {
                "total": await uow.users.count_total(),
                "active_today": await uow.users.count_active(days=1),
                "active_week": await uow.users.count_active(days=7),
            },
            "entities": {
                "groups": len(await uow.groups.get_all()),
                "teachers": len(await uow.teachers.get_all()),
                "subjects": len(await uow.subjects.get_all()),
            },
            "requests": await uow.user_requests.count_by_type(days=7)
        }

    return stats


# ========== ЗАГРУЗКА РАСПИСАНИЯ ==========

@app.get("/upload-schedule", response_class=HTMLResponse, tags=["Web UI"])
async def upload_schedule_form(request: Request):
    """Форма для загрузки расписания"""
    async with UnitOfWork() as uow:
        groups = await uow.groups.get_all()

    return templates.TemplateResponse("upload_schedule.html", {
        "request": request,
        "groups": groups
    })


@app.post("/upload-schedule", response_class=HTMLResponse, tags=["Web UI"])
async def upload_schedule(
        request: Request,
        group_id: int = Form(...),
        file: UploadFile = File(...),
        replace_existing: bool = Form(False)
):
    """
    Загрузка и парсинг расписания из файла

    Args:
        group_id: ID группы
        file: Файл .doc или .docx с расписанием
        replace_existing: Заменить существующие занятия
    """
    async with UnitOfWork() as uow:
        # Проверяем группу
        group = await uow.groups.get_by_id(group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Группа не найдена")

        # Проверяем расширение файла
        if not file.filename.lower().endswith(('.doc', '.docx')):
            raise HTTPException(
                status_code=400,
                detail="Неподдерживаемый формат. Используйте .doc или .docx"
            )

        # Создаем папку для файлов если её нет
        month_name = datetime.now().strftime("%B_%Y")
        upload_dir = Path(f"files/{month_name}")
        upload_dir.mkdir(parents=True, exist_ok=True)

        # Сохраняем файл
        file_path = upload_dir / file.filename
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        try:
            # Конвертируем .doc в .docx если нужно
            if file.filename.lower().endswith('.doc'):
                file_path = Path(convert_doc_to_docx(str(file_path)))

            # Парсим расписание
            lessons = parse_docx_schedule(str(file_path), group.group_name)

            if not lessons:
                raise HTTPException(
                    status_code=400,
                    detail="Не удалось распарсить расписание. Проверьте формат файла."
                )

            # Получаем диапазон дат
            dates = [lesson["start_datetime"] for lesson in lessons]
            min_date = min(dates).date()
            max_date = max(dates).date()

            # Удаляем существующие занятия если нужно
            if replace_existing:
                deleted_count = await uow.lessons.delete_by_group_and_range(
                    group.group_id,
                    min_date,
                    max_date
                )
                print(f"🗑 Удалено старых занятий: {deleted_count}")

            # Импортируем в БД
            imported_count = await import_schedule_to_db_async(lessons, uow)
            await uow.commit()

            return templates.TemplateResponse("upload_success.html", {
                "request": request,
                "group": group,
                "lessons_count": imported_count,
                "date_from": format_date(min_date),
                "date_to": format_date(max_date)
            })

        except Exception as e:
            await uow.rollback()
            print(f"❌ Ошибка обработки файла: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Ошибка обработки файла: {str(e)}"
            )


# ========== API - РАСПИСАНИЕ ==========

@app.get("/api/schedule/{group_name}/{date}", tags=["Schedule"])
async def get_schedule(
        group_name: str,
        date: str,  # Формат: YYYY-MM-DD
):
    """
    Получить расписание группы на конкретную дату

    Args:
        group_name: Название группы (например, "Э-42")
        date: Дата в формате YYYY-MM-DD
    """
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Некорректный формат даты. Используйте YYYY-MM-DD"
        )

    async with UnitOfWork() as uow:
        group = await uow.groups.get_by_name(group_name)
        if not group:
            raise HTTPException(status_code=404, detail="Группа не найдена")

        lessons = await uow.lessons.get_by_group_and_date(group.group_id, target_date)

    return {
        "group": group_name,
        "date": date,
        "lessons": [
            {
                "id": lesson.lesson_id,
                "subject": lesson.subject.name,
                "teacher": lesson.teacher.name,
                "classroom": lesson.classroom,
                "lesson_type": lesson.lesson_type,
                "start_time": lesson.start_datetime.strftime("%H:%M"),
                "end_time": lesson.end_datetime.strftime("%H:%M"),
            }
            for lesson in lessons
        ]
    }


@app.get("/api/schedule/{group_name}/week", tags=["Schedule"])
async def get_week_schedule(
        group_name: str,
        start_date: Optional[str] = Query(None, description="Дата начала недели (YYYY-MM-DD)")
):
    """Получить расписание группы на неделю"""
    if start_date:
        try:
            week_start = datetime.strptime(start_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Некорректный формат даты")
    else:
        week_start = date.today()

    week_end = week_start + timedelta(days=6)

    async with UnitOfWork() as uow:
        group = await uow.groups.get_by_name(group_name)
        if not group:
            raise HTTPException(status_code=404, detail="Группа не найдена")

        lessons = await uow.lessons.get_by_group_and_range(
            group.group_id,
            week_start,
            week_end
        )

    # Группируем по дням
    schedule_by_day = {}
    for lesson in lessons:
        day = lesson.start_datetime.date().isoformat()
        if day not in schedule_by_day:
            schedule_by_day[day] = []

        schedule_by_day[day].append({
            "id": lesson.lesson_id,
            "subject": lesson.subject.name,
            "teacher": lesson.teacher.name,
            "classroom": lesson.classroom,
            "lesson_type": lesson.lesson_type,
            "start_time": lesson.start_datetime.strftime("%H:%M"),
            "end_time": lesson.end_datetime.strftime("%H:%M"),
        })

    return {
        "group": group_name,
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "schedule": schedule_by_day
    }


# ========== CRUD: ГРУППЫ ==========

@app.get("/groups", response_class=HTMLResponse, tags=["Web UI"])
async def list_groups_page(request: Request):
    """Страница со списком групп"""
    async with UnitOfWork() as uow:
        groups = await uow.groups.get_all()

    return templates.TemplateResponse("groups_list.html", {
        "request": request,
        "groups": groups
    })


@app.get("/add-group", response_class=HTMLResponse, tags=["Web UI"])
async def add_group_form(request: Request):
    """Форма добавления группы"""
    return templates.TemplateResponse("add_group.html", {"request": request})


@app.post("/add-group", tags=["Web UI"])
async def add_group(group_name: str = Form(...)):
    """Создать новую группу"""
    async with UnitOfWork() as uow:
        # Проверяем, не существует ли уже
        existing = await uow.groups.get_by_name(group_name)
        if existing:
            raise HTTPException(status_code=400, detail="Группа с таким названием уже существует")

        await uow.groups.create(group_name)
        await uow.commit()

    return RedirectResponse("/", status_code=303)


@app.get("/group/{group_id}", response_class=HTMLResponse, tags=["Web UI"])
async def view_group(request: Request, group_id: int):
    """Детальная информация о группе"""
    async with UnitOfWork() as uow:
        group = await uow.groups.get_by_id(group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Группа не найдена")

        # Получаем занятия на следующие 14 дней
        today = date.today()
        end_date = today + timedelta(days=14)
        lessons = await uow.lessons.get_by_group_and_range(group_id, today, end_date)

        # Получаем студентов группы
        students = await uow.users.get_by_group(group_id)

    return templates.TemplateResponse("group_detail.html", {
        "request": request,
        "group": group,
        "lessons": lessons,
        "students": students
    })


@app.get("/edit-group/{group_id}", response_class=HTMLResponse, tags=["Web UI"])
async def edit_group_form(request: Request, group_id: int):
    """Форма редактирования группы"""
    async with UnitOfWork() as uow:
        group = await uow.groups.get_by_id(group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Группа не найдена")

    return templates.TemplateResponse("edit_group.html", {
        "request": request,
        "group": group
    })


@app.post("/update-group/{group_id}", tags=["Web UI"])
async def update_group(group_id: int, group_name: str = Form(...)):
    """Обновить группу"""
    async with UnitOfWork() as uow:
        group = await uow.groups.update(group_id, group_name)
        if not group:
            raise HTTPException(status_code=404, detail="Группа не найдена")
        await uow.commit()

    return RedirectResponse("/", status_code=303)


@app.post("/delete-group/{group_id}", tags=["Web UI"])
async def delete_group(group_id: int):
    """Удалить группу"""
    async with UnitOfWork() as uow:
        success = await uow.groups.delete(group_id)
        if not success:
            raise HTTPException(status_code=404, detail="Группа не найдена")
        await uow.commit()

    return RedirectResponse("/", status_code=303)


# ========== API ЭНДПОИНТЫ - ГРУППЫ ==========

@app.get("/api/groups", tags=["Groups"])
async def api_list_groups():
    """API: Получить список всех групп"""
    async with UnitOfWork() as uow:
        groups = await uow.groups.get_all()

    return [
        {
            "id": group.group_id,
            "name": group.group_name,
            "students_count": len(group.students) if group.students else 0
        }
        for group in groups
    ]


@app.get("/api/groups/{group_id}", tags=["Groups"])
async def api_get_group(group_id: int):
    """API: Получить информацию о группе"""
    async with UnitOfWork() as uow:
        group = await uow.groups.get_by_id(group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Группа не найдена")

    return {
        "id": group.group_id,
        "name": group.group_name,
        "students": [
            {
                "id": student.id,
                "user_id": student.user_id,
                "username": student.username
            }
            for student in (group.students or [])
        ]
    }


# ========== CRUD: ПРЕПОДАВАТЕЛИ ==========

@app.get("/add-teacher", response_class=HTMLResponse, tags=["Web UI"])
async def add_teacher_form(request: Request):
    """Форма добавления преподавателя"""
    return templates.TemplateResponse("add_teacher.html", {"request": request})


@app.post("/add-teacher", tags=["Web UI"])
async def add_teacher(
        name: str = Form(...),
        email: Optional[str] = Form(None),
        phone: Optional[str] = Form(None)
):
    """Создать нового преподавателя"""
    async with UnitOfWork() as uow:
        await uow.teachers.create(name, email, phone)
        await uow.commit()

    return RedirectResponse("/", status_code=303)


@app.get("/teacher/{teacher_id}", response_class=HTMLResponse, tags=["Web UI"])
async def view_teacher(request: Request, teacher_id: int):
    """Детальная информация о преподавателе"""
    async with UnitOfWork() as uow:
        teacher = await uow.teachers.get_by_id(teacher_id)
        if not teacher:
            raise HTTPException(status_code=404, detail="Преподаватель не найден")

        # Получаем занятия преподавателя на следующие 14 дней
        today = date.today()
        end_date = today + timedelta(days=14)

        result = await uow.session.execute(
            select(Lesson)
            .where(Lesson.teacher_id == teacher_id)
            .where(Lesson.start_datetime >= datetime.combine(today, datetime.min.time()))
            .where(Lesson.start_datetime <= datetime.combine(end_date, datetime.max.time()))
            .options(
                selectinload(Lesson.group),
                selectinload(Lesson.subject)
            )
            .order_by(Lesson.start_datetime)
        )
        lessons = result.scalars().all()

    return templates.TemplateResponse("teacher_detail.html", {
        "request": request,
        "teacher": teacher,
        "lessons": lessons
    })


@app.get("/edit-teacher/{teacher_id}", response_class=HTMLResponse, tags=["Web UI"])
async def edit_teacher_form(request: Request, teacher_id: int):
    """Форма редактирования преподавателя"""
    async with UnitOfWork() as uow:
        teacher = await uow.teachers.get_by_id(teacher_id)
        if not teacher:
            raise HTTPException(status_code=404, detail="Преподаватель не найден")

    return templates.TemplateResponse("edit_teacher.html", {
        "request": request,
        "teacher": teacher
    })


@app.post("/update-teacher/{teacher_id}", tags=["Web UI"])
async def update_teacher(
        teacher_id: int,
        name: str = Form(...),
        email: Optional[str] = Form(None),
        phone: Optional[str] = Form(None)
):
    """Обновить преподавателя"""
    async with UnitOfWork() as uow:
        teacher = await uow.teachers.get_by_id(teacher_id)
        if not teacher:
            raise HTTPException(status_code=404, detail="Преподаватель не найден")

        teacher.name = name
        teacher.email = email
        teacher.phone = phone
        await uow.commit()

    return RedirectResponse("/", status_code=303)


@app.post("/delete-teacher/{teacher_id}", tags=["Web UI"])
async def delete_teacher(teacher_id: int):
    """Удалить преподавателя"""
    async with UnitOfWork() as uow:
        result = await uow.session.execute(
            select(Teacher).where(Teacher.teacher_id == teacher_id)
        )
        teacher = result.scalar_one_or_none()

        if not teacher:
            raise HTTPException(status_code=404, detail="Преподаватель не найден")

        await uow.session.delete(teacher)
        await uow.commit()

    return RedirectResponse("/", status_code=303)


# ========== CRUD: ПРЕДМЕТЫ ==========

@app.get("/add-subject", response_class=HTMLResponse, tags=["Web UI"])
async def add_subject_form(request: Request):
    """Форма добавления предмета"""
    return templates.TemplateResponse("add_subject.html", {"request": request})


@app.post("/add-subject", tags=["Web UI"])
async def add_subject(name: str = Form(...)):
    """Создать новый предмет"""
    async with UnitOfWork() as uow:
        await uow.subjects.create(name)
        await uow.commit()

    return RedirectResponse("/", status_code=303)


@app.get("/subject/{subject_id}", response_class=HTMLResponse, tags=["Web UI"])
async def view_subject(request: Request, subject_id: int):
    """Детальная информация о предмете"""
    async with UnitOfWork() as uow:
        subject = await uow.subjects.get_by_id(subject_id)
        if not subject:
            raise HTTPException(status_code=404, detail="Предмет не найден")

    return templates.TemplateResponse("subject_detail.html", {
        "request": request,
        "subject": subject
    })


@app.get("/edit-subject/{subject_id}", response_class=HTMLResponse, tags=["Web UI"])
async def edit_subject_form(request: Request, subject_id: int):
    """Форма редактирования предмета"""
    async with UnitOfWork() as uow:
        subject = await uow.subjects.get_by_id(subject_id)
        if not subject:
            raise HTTPException(status_code=404, detail="Предмет не найден")

    return templates.TemplateResponse("edit_subject.html", {
        "request": request,
        "subject": subject
    })


@app.post("/update-subject/{subject_id}", tags=["Web UI"])
async def update_subject(subject_id: int, name: str = Form(...)):
    """Обновить предмет"""
    async with UnitOfWork() as uow:
        subject = await uow.subjects.get_by_id(subject_id)
        if not subject:
            raise HTTPException(status_code=404, detail="Предмет не найден")

        subject.name = name
        await uow.commit()

    return RedirectResponse("/", status_code=303)


@app.post("/delete-subject/{subject_id}", tags=["Web UI"])
async def delete_subject(subject_id: int):
    """Удалить предмет"""
    async with UnitOfWork() as uow:
        result = await uow.session.execute(
            select(Subject).where(Subject.subject_id == subject_id)
        )
        subject = result.scalar_one_or_none()

        if not subject:
            raise HTTPException(status_code=404, detail="Предмет не найден")

        await uow.session.delete(subject)
        await uow.commit()

    return RedirectResponse("/", status_code=303)


# ========== CRUD: ЗАНЯТИЯ ==========

@app.get("/add-lesson", response_class=HTMLResponse, tags=["Web UI"])
async def add_lesson_form(request: Request):
    """Форма добавления занятия"""
    async with UnitOfWork() as uow:
        groups = await uow.groups.get_all()
        teachers = await uow.teachers.get_all()
        subjects = await uow.subjects.get_all()

    return templates.TemplateResponse("add_lesson.html", {
        "request": request,
        "groups": groups,
        "teachers": teachers,
        "subjects": subjects
    })


@app.post("/add-lesson", tags=["Web UI"])
async def add_lesson(
        start_datetime: str = Form(...),
        group_id: int = Form(...),
        teacher_id: int = Form(...),
        classroom: str = Form(...),
        subject_id: int = Form(...),
        lesson_type: Optional[str] = Form(None)
):
    """Создать новое занятие"""
    start_dt = datetime.fromisoformat(start_datetime)
    end_dt = start_dt + timedelta(minutes=80)

    async with UnitOfWork() as uow:
        await uow.lessons.create(
            start_datetime=start_dt,
            end_datetime=end_dt,
            group_id=group_id,
            teacher_id=teacher_id,
            subject_id=subject_id,
            classroom=classroom,
            lesson_type=lesson_type
        )
        await uow.commit()

    return RedirectResponse("/", status_code=303)


@app.get("/lesson/{lesson_id}", response_class=HTMLResponse, tags=["Web UI"])
async def view_lesson(request: Request, lesson_id: int):
    """Детальная информация о занятии"""
    async with UnitOfWork() as uow:
        lesson = await uow.lessons.get_by_id(lesson_id)
        if not lesson:
            raise HTTPException(status_code=404, detail="Занятие не найдено")

    return templates.TemplateResponse("lesson_detail.html", {
        "request": request,
        "lesson": lesson
    })


@app.get("/edit-lesson/{lesson_id}", response_class=HTMLResponse, tags=["Web UI"])
async def edit_lesson_form(request: Request, lesson_id: int):
    """Форма редактирования занятия"""
    async with UnitOfWork() as uow:
        lesson = await uow.lessons.get_by_id(lesson_id)
        if not lesson:
            raise HTTPException(status_code=404, detail="Занятие не найдено")

        groups = await uow.groups.get_all()
        teachers = await uow.teachers.get_all()
        subjects = await uow.subjects.get_all()

    return templates.TemplateResponse("edit_lesson.html", {
        "request": request,
        "lesson": lesson,
        "groups": groups,
        "teachers": teachers,
        "subjects": subjects
    })


@app.post("/update-lesson/{lesson_id}", tags=["Web UI"])
async def update_lesson(
        lesson_id: int,
        start_datetime: str = Form(...),
        group_id: int = Form(...),
        teacher_id: int = Form(...),
        classroom: str = Form(...),
        subject_id: int = Form(...),
        lesson_type: Optional[str] = Form(None)
):
    """Обновить занятие"""
    start_dt = datetime.fromisoformat(start_datetime)
    end_dt = start_dt + timedelta(minutes=80)

    async with UnitOfWork() as uow:
        lesson = await uow.lessons.get_by_id(lesson_id)
        if not lesson:
            raise HTTPException(status_code=404, detail="Занятие не найдено")

        lesson.start_datetime = start_dt
        lesson.end_datetime = end_dt
        lesson.group_id = group_id
        lesson.teacher_id = teacher_id
        lesson.subject_id = subject_id
        lesson.classroom = classroom
        lesson.lesson_type = lesson_type

        await uow.commit()

    return RedirectResponse("/", status_code=303)


@app.post("/delete-lesson/{lesson_id}", tags=["Web UI"])
async def delete_lesson(lesson_id: int):
    """Удалить занятие"""
    async with UnitOfWork() as uow:
        result = await uow.session.execute(
            select(Lesson).where(Lesson.lesson_id == lesson_id)
        )
        lesson = result.scalar_one_or_none()

        if not lesson:
            raise HTTPException(status_code=404, detail="Занятие не найдено")

        await uow.session.delete(lesson)
        await uow.commit()

    return RedirectResponse("/", status_code=303)


# ========== API - ПОЛЬЗОВАТЕЛИ ==========

@app.get("/api/users", tags=["Users"])
async def api_list_users(
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0)
):
    """API: Получить список пользователей"""
    async with UnitOfWork() as uow:
        users = await uow.users.get_all(limit=limit, offset=offset)

    return [
        {
            "id": user.id,
            "user_id": user.user_id,
            "username": user.username,
            "group": user.group.group_name if user.group else None,
            "created_at": user.created_at.isoformat(),
            "last_activity": user.last_activity.isoformat(),
            "total_requests": user.total_requests
        }
        for user in users
    ]


@app.get("/api/users/{user_id}", tags=["Users"])
async def api_get_user(user_id: int):
    """API: Получить информацию о пользователе по Telegram ID"""
    async with UnitOfWork() as uow:
        user = await uow.users.get_by_telegram_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        # Получаем последние запросы
        requests = await uow.user_requests.get_user_requests(user.id, limit=10)

    return {
        "id": user.id,
        "user_id": user.user_id,
        "username": user.username,
        "group": user.group.group_name if user.group else None,
        "created_at": user.created_at.isoformat(),
        "last_activity": user.last_activity.isoformat(),
        "total_requests": user.total_requests,
        "recent_requests": [
            {
                "type": req.request_type,
                "data": req.request_data,
                "timestamp": req.timestamp.isoformat()
            }
            for req in requests
        ]
    }


# ========== ЗАПУСК ПРИЛОЖЕНИЯ ==========

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api:app",
        port=8000,
        reload=True,  # Автоперезагрузка при изменениях (только для dev)
        log_level="info"
    )

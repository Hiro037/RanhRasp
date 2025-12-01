import os

from fastapi import FastAPI, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
from fastapi.staticfiles import StaticFiles

from create_database import Group, Teacher, Subject, Lesson, session
from test_parse import parse_docx_schedule, import_schedule_to_db

app = FastAPI()
templates = Jinja2Templates(directory="templates")

os.makedirs("files", exist_ok=True)
app.mount("/files", StaticFiles(directory="files"), name="files")

# Главная страница с просмотром всех сущностей
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    groups = session.query(Group).order_by(Group.group_name).all()
    teachers = session.query(Teacher).order_by(Teacher.name).all()
    subjects = session.query(Subject).order_by(Subject.name).all()
    lessons = session.query(Lesson).order_by(Lesson.start_datetime).all()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "groups": groups,
        "teachers": teachers,
        "subjects": subjects,
        "lessons": lessons
    })

# Добавление расписания из файла
@app.get("/upload-schedule", response_class=HTMLResponse)
def upload_schedule_form(request: Request):
    groups = session.query(Group).order_by(Group.group_name).all()
    return templates.TemplateResponse("upload_schedule.html", {
        "request": request,
        "groups": groups
    })


@app.post("/upload-schedule")
async def upload_schedule(
        request: Request,
        group_id: int = Form(...),
        file: UploadFile = File(...)
):
    # Проверяем группу
    group = session.query(Group).filter(Group.group_id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Сохраняем файл
    file_path = f"files/{file.filename}"
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    try:
        # Парсим расписание
        lessons_data = parse_docx_schedule(file_path, group.group_name)

        # Импортируем в БД
        import_schedule_to_db(lessons_data)

        return templates.TemplateResponse("upload_success.html", {
            "request": request,
            "group": group,
            "lessons_count": len(lessons_data)
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

@app.get("/test")
def test():
    return {"message": "test"}

# ==== ГРУППЫ ====
@app.get("/add-group", response_class=HTMLResponse)
def add_group_form(request: Request):
    return templates.TemplateResponse("add_group.html", {"request": request})

@app.post("/add-group")
def add_group(group_name: str = Form(...)):
    new_group = Group(group_name=group_name)
    session.add(new_group)
    session.commit()
    return RedirectResponse("/", status_code=303)

@app.get("/group/{group_id}", response_class=HTMLResponse)
def view_group(request: Request, group_id: int):
    group = session.query(Group).filter(Group.group_id == group_id).first()
    group_lessons = session.query(Lesson).filter(Lesson.group == group).order_by(Lesson.start_datetime).all()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return templates.TemplateResponse("group_detail.html", {"request": request, "group": group, "lessons": group_lessons})

@app.get("/edit-group/{group_id}", response_class=HTMLResponse)
def edit_group_form(request: Request, group_id: int):
    group = session.query(Group).filter(Group.group_id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return templates.TemplateResponse("edit_group.html", {"request": request, "group": group})

@app.post("/update-group/{group_id}")
def update_group(group_id: int, group_name: str = Form(...)):
    group = session.query(Group).filter(Group.group_id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    group.group_name = group_name
    session.commit()
    return RedirectResponse("/", status_code=303)

@app.post("/delete-group/{group_id}")
def delete_group(group_id: int):
    group = session.query(Group).filter(Group.group_id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    session.delete(group)
    session.commit()
    return RedirectResponse("/", status_code=303)

# ==== ПРЕПОДАВАТЕЛИ ====
@app.get("/add-teacher", response_class=HTMLResponse)
def add_teacher_form(request: Request):
    return templates.TemplateResponse("add_teacher.html", {"request": request})

@app.post("/add-teacher")
def add_teacher(name: str = Form(...)):
    new_teacher = Teacher(name=name)
    session.add(new_teacher)
    session.commit()
    return RedirectResponse("/", status_code=303)

@app.get("/teacher/{teacher_id}", response_class=HTMLResponse)
def view_teacher(request: Request, teacher_id: int):
    teacher = session.query(Teacher).filter(Teacher.teacher_id == teacher_id).first()
    teachers_lessons = session.query(Lesson).filter(Lesson.teacher == teacher).order_by(Lesson.start_datetime).all()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    return templates.TemplateResponse("teacher_detail.html", {"request": request, "teacher": teacher, "lessons": teachers_lessons})

@app.get("/edit-teacher/{teacher_id}", response_class=HTMLResponse)
def edit_teacher_form(request: Request, teacher_id: int):
    teacher = session.query(Teacher).filter(Teacher.teacher_id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    return templates.TemplateResponse("edit_teacher.html", {"request": request, "teacher": teacher})

@app.post("/update-teacher/{teacher_id}")
def update_teacher(teacher_id: int, name: str = Form(...)):
    teacher = session.query(Teacher).filter(Teacher.teacher_id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    teacher.name = name
    session.commit()
    return RedirectResponse("/", status_code=303)

@app.post("/delete-teacher/{teacher_id}")
def delete_teacher(teacher_id: int):
    teacher = session.query(Teacher).filter(Teacher.teacher_id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    session.delete(teacher)
    session.commit()
    return RedirectResponse("/", status_code=303)

# ==== ПРЕДМЕТЫ ====
@app.get("/add-subject", response_class=HTMLResponse)
def add_subject_form(request: Request):
    return templates.TemplateResponse("add_subject.html", {"request": request})

@app.post("/add-subject")
def add_subject(name: str = Form(...)):
    new_subject = Subject(name=name)
    session.add(new_subject)
    session.commit()
    return RedirectResponse("/", status_code=303)

@app.get("/subject/{subject_id}", response_class=HTMLResponse)
def view_subject(request: Request, subject_id: int):
    subject = session.query(Subject).filter(Subject.subject_id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    return templates.TemplateResponse("subject_detail.html", {"request": request, "subject": subject})

@app.get("/edit-subject/{subject_id}", response_class=HTMLResponse)
def edit_subject_form(request: Request, subject_id: int):
    subject = session.query(Subject).filter(Subject.subject_id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    return templates.TemplateResponse("edit_subject.html", {"request": request, "subject": subject})

@app.post("/update-subject/{subject_id}")
def update_subject(subject_id: int, name: str = Form(...)):
    subject = session.query(Subject).filter(Subject.subject_id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    subject.name = name
    session.commit()
    return RedirectResponse("/", status_code=303)

@app.post("/delete-subject/{subject_id}")
def delete_subject(subject_id: int):
    subject = session.query(Subject).filter(Subject.subject_id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    session.delete(subject)
    session.commit()
    return RedirectResponse("/", status_code=303)

# ==== ЗАНЯТИЯ ====
@app.get("/add-lesson", response_class=HTMLResponse)
def add_lesson_form(request: Request):
    groups = session.query(Group).all()
    teachers = session.query(Teacher).order_by(Teacher.name).all()
    subjects = session.query(Subject).order_by(Subject.name).all()
    return templates.TemplateResponse("add_lesson.html", {
        "request": request,
        "groups": groups,
        "teachers": teachers,
        "subjects": subjects
    })

@app.post("/add-lesson")
def add_lesson(
    start_datetime: str = Form(...),
    group_id: int = Form(...),
    teacher_id: int = Form(...),
    classroom: str = Form(...),  # Изменил на String
    subject_id: int = Form(...),
    lesson_type: str = Form(None)  # Добавил поле типа занятия
):
    start_dt = datetime.fromisoformat(start_datetime)
    end_dt = start_dt + timedelta(minutes=80)
    lesson = Lesson(
        start_datetime=start_dt,
        end_datetime=end_dt,
        group_id=group_id,
        teacher_id=teacher_id,
        classroom=classroom,
        subject_id=subject_id,
        lesson_type=lesson_type
    )
    session.add(lesson)
    session.commit()
    return RedirectResponse("/", status_code=303)

@app.get("/lesson/{lesson_id}", response_class=HTMLResponse)
def view_lesson(request: Request, lesson_id: int):
    lesson = session.query(Lesson).filter(Lesson.lesson_id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return templates.TemplateResponse("lesson_detail.html", {"request": request, "lesson": lesson})

@app.get("/edit-lesson/{lesson_id}", response_class=HTMLResponse)
def edit_lesson_form(request: Request, lesson_id: int):
    lesson = session.query(Lesson).filter(Lesson.lesson_id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    groups = session.query(Group).all()
    teachers = session.query(Teacher).order_by(Teacher.name).all()
    subjects = session.query(Subject).order_by(Subject.name).all()
    return templates.TemplateResponse("edit_lesson.html", {
        "request": request,
        "lesson": lesson,
        "groups": groups,
        "teachers": teachers,
        "subjects": subjects
    })

@app.post("/update-lesson/{lesson_id}")
def update_lesson(
    lesson_id: int,
    start_datetime: str = Form(...),
    group_id: int = Form(...),
    teacher_id: int = Form(...),
    classroom: str = Form(...),  # Изменил на String
    subject_id: int = Form(...),
    lesson_type: str = Form(None)  # Добавил поле типа занятия
):
    lesson = session.query(Lesson).filter(Lesson.lesson_id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    start_dt = datetime.fromisoformat(start_datetime)
    end_dt = start_dt + timedelta(minutes=80)
    lesson.start_datetime = start_dt
    lesson.end_datetime = end_dt
    lesson.group_id = group_id
    lesson.teacher_id = teacher_id
    lesson.classroom = classroom
    lesson.subject_id = subject_id
    lesson.lesson_type = lesson_type
    session.commit()
    return RedirectResponse("/", status_code=303)

@app.post("/delete-lesson/{lesson_id}")
def delete_lesson(lesson_id: int):
    lesson = session.query(Lesson).filter(Lesson.lesson_id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    session.delete(lesson)
    session.commit()
    return RedirectResponse("/", status_code=303)
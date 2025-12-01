import re
import subprocess
from datetime import datetime, timedelta
from docx import Document

from create_database import Session, Group, Teacher, Subject, Lesson

# TODO: изменить эти функции так, чтоб главная функция принимала на вход файл и название группы, а затем переносила данные в БД

# Вспомогательные функции
def get_or_create(session, model, attr, value):
    instance = session.query(model).filter(getattr(model, attr) == value).first()
    if not instance:
        instance = model(**{attr: value})
        session.add(instance)
        session.commit()
    return instance

def parse_time_range(time_str):
    start_str, end_str = time_str.split("-")
    start_str = start_str.replace(".", ":")
    end_str = end_str.replace(".", ":")
    t_start = datetime.strptime(start_str, "%H:%M").time()
    t_end = datetime.strptime(end_str, "%H:%M").time()
    return t_start, t_end

def split_subject(cell):
    # Логика типа "Макроэкономика (л)" -> subject, lesson_type
    m = re.search(r"\((л|пр)\)", cell)
    lesson_type = m.group(1) if m else None
    subject = re.sub(r"\s*\((л|пр)\)", "", cell).replace("Зачёт", "").replace(".", "").strip()
    return subject, lesson_type

def extract_fio(teacher_str):
    # Находим шаблон "Фамилия И.О." в конце строки
    match = re.search(r'([А-ЯЁA-Z][а-яёa-z]+ [А-ЯA-Z]\.[А-ЯA-Z]\.)$', teacher_str)
    if match:
        return match.group(1)
    # Находим шаблон "Фамилия И.О."
    match = re.search(r'([А-ЯЁA-Z][а-яёa-z]+ [А-ЯA-Z]\.[А-ЯA-Z]\.)', teacher_str)
    if match:
        return match.group(1)
    return teacher_str.strip()

def parse_docx_schedule(docx_path, group_name="Э-42"):
    doc = Document(docx_path)
    table = doc.tables[0]  # расписание - одна таблица
    lessons = []
    date_re = re.compile(r"(\d{2}\.\d{2}\.\d{2})\s+г\s+(\S+)")  # "01.11.25 г Суббота"

    current_date = None
    # первая строка - заголовок
    for row in table.rows[1:]:
        cells = [c.text.strip() for c in row.cells]
        date_cell, time_cell, subject_cell, teacher_cell, room_cell = (cells + [""] * 5)[:5]

        # Обработка даты
        if date_cell:
            m = date_re.search(date_cell)
            if not m: continue
            date_obj = datetime.strptime(m.group(1), "%d.%m.%y").date()
            current_date = date_obj
        if not current_date or not time_cell or not subject_cell:
            continue

        t_start, t_end = parse_time_range(time_cell)
        subject, lesson_type = split_subject(subject_cell)
        teacher_name = extract_fio(teacher_cell.strip())
        room = room_cell.strip() if room_cell.strip() else None

        # Строим datetime (для твоей модели start_datetime, end_datetime)
        dt_start = datetime.combine(current_date, t_start)
        dt_end = datetime.combine(current_date, t_end)

        lessons.append({
            "group": group_name,
            "subject": subject,
            "lesson_type": lesson_type,
            "teacher": teacher_name,
            "classroom": room,
            "start_datetime": dt_start,
            "end_datetime": dt_end,
        })
    return lessons

def import_schedule_to_db(lessons):
    session = Session()
    for l in lessons:
        # Преподаватель
        teacher = get_or_create(session, Teacher, 'name', l["teacher"])
        # Предмет
        subject = get_or_create(session, Subject, 'name', l["subject"])
        # Группа
        group = get_or_create(session, Group, 'group_name', l["group"])
        # lesson_type НЕ записывается - если поле не добавлено!
        lesson = Lesson(
            start_datetime=l["start_datetime"],
            end_datetime=l["end_datetime"],
            group_id=group.group_id,
            teacher_id=teacher.teacher_id,
            classroom=l["classroom"],
            subject_id=subject.subject_id,
            lesson_type=l["lesson_type"],
        )
        session.add(lesson)
    session.commit()
    print("Импорт завершён!")
    session.close()

def convert_doc_to_docx(input_path):
    subprocess.run([
        "libreoffice",
        "--headless",
        "--convert-to",
        "docx",
        input_path
    ], check=True)


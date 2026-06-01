#!/usr/bin/env python3
"""
Парсер расписания из DOC/DOCX файлов.
Исправленная версия с корректной работой с async_session.
"""

import argparse
import asyncio
import os
from datetime import datetime, date, time
from docx import Document
from sqlalchemy import select
import aspose.words as aw
import re

from database.connection import async_session
from database.models import Group, Subject, Classroom, Teacher, Lesson, LessonGroup
from parser.regex_patterns import DATE_PATTERN, TIME_START_PATTERN, ACADEMIC_TITLES_PATTERN, CLEAN_NAME_PATTERN
from utils.timezone import YEKT_TZ


def ensure_docx(file_path: str) -> tuple[str, bool]:
    """
    Проверяет формат файла. Если это .doc, конвертирует его в .docx.
    Возвращает (путь_к_docx_файлу, был_ли_файл_создан_временно).
    """
    if file_path.endswith(".doc"):
        print("[Конвертер] Обнаружен старый формат .doc. Автоматически переводим в .docx...")
        doc = aw.Document(file_path)
        docx_path = file_path + "x"  # Получится путь вида "расписание.docx"
        doc.save(docx_path)
        return docx_path, True  # True означает, что файл временный и его надо удалить
    return file_path, False


def clean_and_split_row(line: str) -> list[str]:
    """Разбивает строку таблицы по символу ячейки и убирает пустые элементы."""
    return [p.strip() for p in line.split("")]


def parse_date(text: str) -> date | None:
    """Извлекает дату, приводя двухзначный год к четырёхзначному (26 -> 2026)."""
    match = DATE_PATTERN.search(text)
    if match:
        day, month, year = match.groups()
        if len(year) == 2:
            year = "20" + year
        return date(int(year), int(month), int(day))
    return None


def parse_start_time(text: str) -> time | None:
    """Извлекает время начала (10.00 -> 10:00)."""
    match = TIME_START_PATTERN.search(text)
    if match:
        hours, minutes = match.groups()
        return time(int(hours), int(minutes))
    return None


def clean_teacher_name(text: str) -> str:
    """Очищает строку от учёных степеней (доц., к.э.н.) и возвращает ФИО."""
    no_titles = ACADEMIC_TITLES_PATTERN.sub("", text)
    match = CLEAN_NAME_PATTERN.search(no_titles)
    if match:
        return match.group(0).strip()
    return no_titles.strip()


def determine_lesson_type(subject_text: str) -> str:
    """Определяет тип занятия по маркерам (л), (пр)."""
    text_lower = subject_text.lower()
    if "(л)" in text_lower or "лекция" in text_lower:
        return "лекция"
    if "(пр)" in text_lower or "практика" in text_lower:
        return "практика"
    if "(конс)" in text_lower or "консультация" in text_lower:
        return "консультация"
    if "зачёт с оценкой" in text_lower or "диф.зачет" in text_lower:
        return "зачет с оценкой"
    if "зачёт" in text_lower:
        return "зачет"
    if "экзамен" in text_lower:
        return "экзамен"
    return "другое"


def clean_subject_name(text: str) -> str:
    """Очищает название предмета от мусора."""
    text = re.sub(r"\(л\)?|\(пр\)?|\(конс\)?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\.\s*Зачёт.*", "", text, flags=re.IGNORECASE)
    return text.strip(",. -()")


async def get_or_create(session, model, field, value: str):
    """Универсальный метод получения или создания объекта."""
    stmt = select(model).where(field == value)
    result = await session.execute(stmt)
    obj = result.scalars().first()
    if not obj:
        obj = model(**{field.name: value})
        session.add(obj)
        await session.flush()
    return obj


async def parse_docx_to_db(file_path: str, group_name: str):
    """Основная функция импорта расписания из файла."""
    target_file, is_temporary = ensure_docx(file_path)
    print(f"[Парсер] Начинаем чтение сетки расписания из: {target_file}")

    doc = Document(target_file)
    lines = []

    for p in doc.paragraphs:
        if p.text.strip():
            lines.append(p.text)
    for table in doc.tables:
        for row in table.rows:
            row_text = "".join([cell.text.strip() for cell in row.cells])
            if row_text.strip(" "):
                lines.append(row_text)

    # Используем async_session как контекстный менеджер
    async with async_session() as session:
        group_obj = await get_or_create(session, Group, Group.name, group_name)
        current_date: date | None = None

        for line in lines:
            parts = clean_and_split_row(line)
            extracted_date = parse_date(line)
            if extracted_date:
                current_date = extracted_date

            row_time = None
            time_cell_idx = -1
            for idx, part in enumerate(parts):
                parsed_t = parse_start_time(part)
                if parsed_t and ("-" in part or "." in part or ":" in part):
                    row_time = parsed_t
                    time_cell_idx = idx
                    break

            if not row_time or not current_date:
                continue

            try:
                subject_raw = parts[time_cell_idx + 1]
                teacher_raw = parts[time_cell_idx + 2] if (time_cell_idx + 2) < len(parts) else ""
                classroom_raw = parts[time_cell_idx + 3] if (time_cell_idx + 3) < len(parts) else "Ауд. не указана"
            except IndexError:
                continue

            if not subject_raw:
                continue

            start_datetime = datetime.combine(current_date, row_time).replace(tzinfo=YEKT_TZ)
            lesson_type = determine_lesson_type(subject_raw)
            subject_name = clean_subject_name(subject_raw)
            teacher_name = clean_teacher_name(teacher_raw) if teacher_raw else "Не указан"
            classroom_name = classroom_raw.strip() if classroom_raw else "---"

            subject_obj = await get_or_create(session, Subject, Subject.name, subject_name[:150])
            classroom_obj = await get_or_create(session, Classroom, Classroom.name, classroom_name[:50])

            teacher_obj = None
            if teacher_name != "Не указан":
                teacher_obj = await get_or_create(session, Teacher, Teacher.name, teacher_name)

            lesson_stmt = select(Lesson).where(
                Lesson.start_datetime == start_datetime,
                Lesson.subject_id == subject_obj.id,
                Lesson.classroom_id == classroom_obj.id
            )
            lesson_res = await session.execute(lesson_stmt)
            lesson_obj = lesson_res.scalars().first()

            if not lesson_obj:
                lesson_obj = Lesson(
                    start_datetime=start_datetime,
                    type=lesson_type,
                    classroom_id=classroom_obj.id,
                    teacher_id=teacher_obj.id if teacher_obj else None,
                    subject_id=subject_obj.id,
                    comment=None
                )
                session.add(lesson_obj)
                await session.flush()
                print(f" -> Добавлено: {current_date} [{row_time}] {subject_name}")

            link_stmt = select(LessonGroup).where(
                LessonGroup.lesson_id == lesson_obj.id,
                LessonGroup.group_id == group_obj.id
            )
            link_res = await session.execute(link_stmt)
            if not link_res.scalars().first():
                new_link = LessonGroup(lesson_id=lesson_obj.id, group_id=group_obj.id)
                session.add(new_link)

        await session.commit()
        print("[Парсер] Импорт завершён!")

    if is_temporary and os.path.exists(target_file):
        os.remove(target_file)
        print("[Конвертер] Временный файл .docx успешно удалён.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=str, required=True)
    parser.add_argument("--group", type=str, required=True)
    args = parser.parse_args()

    asyncio.run(parse_docx_to_db(args.file, args.group))
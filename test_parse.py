"""
Модуль для парсинга расписания из документов Word (.doc/.docx)

Основные функции:
- parse_docx_schedule: парсинг расписания из .docx файла
- import_schedule_to_db_async: асинхронный импорт расписания в БД
- convert_doc_to_docx: конвертация .doc в .docx через LibreOffice
"""

import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from docx import Document

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========


def parse_time_range(time_str: str) -> tuple[datetime.time, datetime.time]:
    """
    Парсит строку времени вида "09.00-10.20" или "09:00-10:20"

    Args:
        time_str: Строка с диапазоном времени

    Returns:
        tuple[time, time]: Время начала и окончания
    """
    normalized = time_str.replace("–", "-").replace("—", "-")
    start_str, end_str = normalized.split("-", maxsplit=1)
    start_str = start_str.replace(".", ":")
    end_str = end_str.replace(".", ":")
    t_start = datetime.strptime(start_str.strip(), "%H:%M").time()
    t_end = datetime.strptime(end_str.strip(), "%H:%M").time()
    return t_start, t_end


def split_subject(cell: str) -> tuple[str, Optional[str]]:
    """
    Разделяет предмет и тип занятия

    Примеры:
        "Макроэкономика (л)" -> ("Макроэкономика", "л")
        "Микроэкономика (пр)" -> ("Микроэкономика", "пр")
        "История" -> ("История", None)

    Args:
        cell: Строка с названием предмета

    Returns:
        tuple[str, str | None]: Предмет и тип занятия
    """
    # Ищем (л) или (пр) в конце
    m = re.search(r"\((л|пр)\)", cell)
    lesson_type = None

    if m:
        lesson_type_code = m.group(1)
        # Расшифровываем тип занятия
        lesson_type = "Лекция" if lesson_type_code == "л" else "Практика"

    # Удаляем тип занятия и лишние слова
    subject = re.sub(r"\s*\((л|пр)\)", "", cell)
    subject = subject.replace("Зачёт", "").replace("Зачет", "").strip()
    subject = re.sub(r"\.+$", "", subject).strip()  # Удаляем точки в конце

    return subject, lesson_type


def extract_fio(teacher_str: str) -> str:
    """
    Извлекает ФИО преподавателя из строки

    Примеры:
        "Иванов И.И." -> "Иванов И.И."
        "каб. 305 Петров П.П." -> "Петров П.П."
        "Сидоров С.С. доц." -> "Сидоров С.С."

    Args:
        teacher_str: Строка с информацией о преподавателе

    Returns:
        str: ФИО преподавателя
    """
    # Находим шаблон "Фамилия И.О." в конце строки
    match = re.search(
        r"([А-ЯЁA-Z][а-яёa-z]+\s+[А-ЯA-Z]\.[А-ЯA-Z]\.)(?:\s+|$)", teacher_str
    )
    if match:
        return match.group(1).strip()

    # Если не нашли, возвращаем очищенную строку
    result = teacher_str.strip()
    # Удаляем должности
    result = re.sub(
        r"\s+(доц\.|проф\.|ст\.\s*преп\.|преп\.)", "", result, flags=re.IGNORECASE
    )
    return result


# ========== ОСНОВНЫЕ ФУНКЦИИ ==========


def parse_docx_schedule(docx_path: str, group_name: str) -> List[Dict]:
    """
    Парсит расписание из .docx файла

    Ожидаемый формат таблицы:
    | Дата          | Время       | Предмет           | Преподаватель | Аудитория |
    | 01.11.25 г Пн | 09.00-10.20 | Макроэкономика(л) | Иванов И.И.   | 305       |

    Args:
        docx_path: Путь к .docx файлу
        group_name: Название группы

    Returns:
        List[Dict]: Список словарей с данными о занятиях

    Raises:
        FileNotFoundError: Если файл не найден
        IndexError: Если структура таблицы некорректна
    """
    doc = Document(docx_path)

    if not doc.tables:
        raise ValueError("В документе нет таблиц")

    table = doc.tables[0]  # Расписание - первая таблица
    lessons = []

    # Регулярное выражение для даты: "01.11.25 г Суббота" или "01.11.25 Суббота"
    date_re = re.compile(r"(\d{2}\.\d{2}\.\d{2})(?:\s*г?\s+\S+)?")

    current_date = None

    # Пропускаем первую строку (заголовок)
    for row_idx, row in enumerate(table.rows[1:], start=2):
        cells = [c.text.strip() for c in row.cells]

        # Обеспечиваем минимум 5 колонок
        while len(cells) < 5:
            cells.append("")

        date_cell, time_cell, subject_cell, teacher_cell, room_cell = cells[:5]

        # Обработка даты
        if date_cell:
            m = date_re.search(date_cell)
            if m:
                try:
                    date_obj = datetime.strptime(m.group(1), "%d.%m.%y").date()
                    current_date = date_obj
                except ValueError as e:
                    print(
                        f"⚠️ Ошибка парсинга даты в строке {row_idx}: {date_cell} - {e}"
                    )
                    continue

        # Пропускаем строки без даты, времени или предмета
        if not current_date or not time_cell or not subject_cell:
            continue

        # Пропускаем пустые предметы
        if not subject_cell.strip() or subject_cell.strip() in ["-", "—", "–"]:
            continue

        try:
            # Парсим время
            t_start, t_end = parse_time_range(time_cell)

            # Парсим предмет и тип занятия
            subject, lesson_type = split_subject(subject_cell)

            # Парсим преподавателя
            teacher_name = extract_fio(teacher_cell) if teacher_cell else "Не указан"

            # Парсим аудиторию
            room = room_cell.strip() if room_cell.strip() else "Не указана"

            # Строим datetime
            dt_start = datetime.combine(current_date, t_start)
            dt_end = datetime.combine(current_date, t_end)

            # Валидация
            if not subject or subject == "":
                print(f"⚠️ Пропущена строка {row_idx}: пустой предмет")
                continue

            lessons.append(
                {
                    "group": group_name,
                    "subject": subject,
                    "lesson_type": lesson_type,
                    "teacher": teacher_name,
                    "classroom": room,
                    "start_datetime": dt_start,
                    "end_datetime": dt_end,
                }
            )

        except Exception as e:
            print(f"⚠️ Ошибка парсинга строки {row_idx}: {e}")
            print(f"   Данные: {cells}")
            continue

    print(f"✅ Успешно распарсено занятий: {len(lessons)}")
    return lessons


async def import_schedule_to_db_async(lessons: List[Dict], uow) -> int:
    """
    Асинхронный импорт расписания в БД

    Args:
        lessons: Список словарей с данными о занятиях
        uow: UnitOfWork для работы с БД

    Returns:
        int: Количество импортированных занятий

    Raises:
        Exception: При ошибке импорта
    """
    imported_count = 0
    skipped_count = 0

    # Получаем или создаем преподавателей и предметы заранее
    teachers_cache = {}
    subjects_cache = {}
    groups_cache = {}

    print("📦 Начало импорта расписания...")

    # Перед повторной загрузкой удаляем старые занятия в затронутом диапазоне дат.
    # Это делает импорт идемпотентным и не плодит дубликаты после исправления файла.
    lessons_by_group = {}
    for lesson_data in lessons:
        lessons_by_group.setdefault(lesson_data["group"], []).append(lesson_data)

    for group_name, group_lessons in lessons_by_group.items():
        group = await uow.groups.get_by_name(group_name)
        if group:
            dates = [item["start_datetime"].date() for item in group_lessons]
            deleted = await uow.lessons.delete_by_group_and_range(
                group.group_id, min(dates), max(dates)
            )
            if deleted:
                print(f"   🧹 Удалено старых занятий для {group_name}: {deleted}")

    for idx, lesson_data in enumerate(lessons, 1):
        try:
            # Получаем/создаем преподавателя
            teacher_name = lesson_data["teacher"]
            if teacher_name not in teachers_cache:
                teacher, created = await uow.teachers.get_or_create(teacher_name)
                teachers_cache[teacher_name] = teacher
                if created:
                    print(f"   ✓ Создан преподаватель: {teacher_name}")
            teacher = teachers_cache[teacher_name]

            # Получаем/создаем предмет
            subject_name = lesson_data["subject"]
            if subject_name not in subjects_cache:
                subject, created = await uow.subjects.get_or_create(subject_name)
                subjects_cache[subject_name] = subject
                if created:
                    print(f"   ✓ Создан предмет: {subject_name}")
            subject = subjects_cache[subject_name]

            # Получаем/создаем группу
            group_name = lesson_data["group"]
            if group_name not in groups_cache:
                group = await uow.groups.get_by_name(group_name)
                if not group:
                    group = await uow.groups.create(group_name)
                    print(f"   ✓ Создана группа: {group_name}")
                groups_cache[group_name] = group
            group = groups_cache[group_name]

            # Проверяем на дубликаты (опционально)
            # Можно добавить проверку существующих занятий

            # Создаем занятие
            await uow.lessons.create(
                start_datetime=lesson_data["start_datetime"],
                end_datetime=lesson_data["end_datetime"],
                group_id=group.group_id,
                teacher_id=teacher.teacher_id,
                subject_id=subject.subject_id,
                classroom=lesson_data["classroom"],
                lesson_type=lesson_data["lesson_type"],
            )

            imported_count += 1

            # Прогресс каждые 10 занятий
            if idx % 10 == 0:
                print(f"   Обработано: {idx}/{len(lessons)}")

        except Exception as e:
            print(f"⚠️ Ошибка импорта занятия {idx}: {e}")
            print(f"   Данные: {lesson_data}")
            skipped_count += 1
            continue

    print(f"\n✅ Импорт завершен!")
    print(f"   Импортировано: {imported_count}")
    if skipped_count > 0:
        print(f"   Пропущено: {skipped_count}")

    return imported_count


def convert_doc_to_docx(input_path: str) -> str:
    """
    Конвертирует .doc файл в .docx используя LibreOffice

    Требования:
        - LibreOffice должен быть установлен
        - Команда 'libreoffice' должна быть доступна в PATH

    Args:
        input_path: Путь к .doc файлу

    Returns:
        str: Путь к созданному .docx файлу

    Raises:
        subprocess.CalledProcessError: Если конвертация не удалась
        FileNotFoundError: Если LibreOffice не найден
    """
    print(f"🔄 Конвертация {input_path} в .docx...")

    try:
        result = subprocess.run(
            [
                "libreoffice",
                "--headless",
                "--convert-to",
                "docx",
                input_path,
                "--outdir",
                str(Path(input_path).parent),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )

        output_path = input_path.rsplit(".", 1)[0] + ".docx"
        print(f"✅ Файл сконвертирован: {output_path}")
        return output_path

    except subprocess.TimeoutExpired:
        raise Exception("Timeout при конвертации файла")
    except subprocess.CalledProcessError as e:
        raise Exception(f"Ошибка конвертации: {e.stderr}")
    except FileNotFoundError:
        raise Exception(
            "LibreOffice не найден. Установите: "
            "apt-get install libreoffice (Linux) или скачайте с libreoffice.org"
        )


# ========== СИНХРОННАЯ ВЕРСИЯ ДЛЯ СОВМЕСТИМОСТИ ==========


def import_schedule_to_db_sync(lessons: List[Dict]) -> int:
    """
    DEPRECATED: Синхронная версия импорта

    Используется только для обратной совместимости.
    Рекомендуется использовать import_schedule_to_db_async

    Args:
        lessons: Список словарей с данными о занятиях

    Returns:
        int: Количество импортированных занятий
    """
    import asyncio

    from database.repositories import UnitOfWork

    print("⚠️ ВНИМАНИЕ: Используется устаревшая синхронная версия импорта")
    print("   Рекомендуется перейти на import_schedule_to_db_async")

    async def _import():
        async with UnitOfWork() as uow:
            count = await import_schedule_to_db_async(lessons, uow)
            await uow.commit()
            return count

    return asyncio.run(_import())


# Алиас для обратной совместимости
import_schedule_to_db = import_schedule_to_db_sync

# ========== УТИЛИТЫ ==========

from pathlib import Path


def validate_schedule_file(file_path: str) -> bool:
    """
    Проверяет, что файл существует и имеет правильное расширение

    Args:
        file_path: Путь к файлу

    Returns:
        bool: True если файл валиден
    """
    path = Path(file_path)

    if not path.exists():
        print(f"❌ Файл не найден: {file_path}")
        return False

    if path.suffix.lower() not in [".doc", ".docx"]:
        print(f"❌ Неподдерживаемый формат: {path.suffix}")
        return False

    return True


def get_schedule_date_range(lessons: List[Dict]) -> tuple[datetime, datetime]:
    """
    Определяет диапазон дат в расписании

    Args:
        lessons: Список словарей с данными о занятиях

    Returns:
        tuple[datetime, datetime]: Минимальная и максимальная даты
    """
    if not lessons:
        return None, None

    dates = [lesson["start_datetime"] for lesson in lessons]
    return min(dates), max(dates)


def print_schedule_summary(lessons: List[Dict]):
    """
    Выводит краткую сводку о расписании

    Args:
        lessons: Список словарей с данными о занятиях
    """
    if not lessons:
        print("📋 Расписание пустое")
        return

    # Подсчет статистики
    subjects = set(l["subject"] for l in lessons)
    teachers = set(l["teacher"] for l in lessons)
    date_range = get_schedule_date_range(lessons)

    print("\n" + "=" * 50)
    print("📋 СВОДКА РАСПИСАНИЯ")
    print("=" * 50)
    print(f"Группа: {lessons[0]['group']}")
    print(f"Всего занятий: {len(lessons)}")
    print(f"Предметов: {len(subjects)}")
    print(f"Преподавателей: {len(teachers)}")

    if date_range[0] and date_range[1]:
        print(
            f"Период: {date_range[0].strftime('%d.%m.%Y')} - {date_range[1].strftime('%d.%m.%Y')}"
        )

    print("\nПредметы:")
    for subject in sorted(subjects):
        count = sum(1 for l in lessons if l["subject"] == subject)
        print(f"  • {subject}: {count} занятий")

    print("=" * 50 + "\n")


# ========== ПРИМЕР ИСПОЛЬЗОВАНИЯ ==========

if __name__ == "__main__":
    import asyncio

    from database.repositories import UnitOfWork

    async def main():
        # Пример использования
        file_path = "files/November/schedule_E-42.docx"
        group_name = "Э-42"

        # Проверяем файл
        if not validate_schedule_file(file_path):
            return

        # Парсим расписание
        print(f"\n📖 Парсинг расписания для группы {group_name}...")
        lessons = parse_docx_schedule(file_path, group_name)

        # Показываем сводку
        print_schedule_summary(lessons)

        # Импортируем в БД
        print("\n💾 Импорт в базу данных...")
        async with UnitOfWork() as uow:
            count = await import_schedule_to_db_async(lessons, uow)
            await uow.commit()

        print(f"\n✅ Готово! Импортировано занятий: {count}")

    asyncio.run(main())

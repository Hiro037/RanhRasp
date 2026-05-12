"""
Модуль для рендеринга HTML расписания в изображения

Использует:
- Jinja2 для шаблонизации HTML
- Playwright (async) для рендеринга в изображение
- Асинхронную работу с БД через UnitOfWork

Функции:
- render_html: создает HTML из данных расписания
- html_to_image: конвертирует HTML в PNG изображение
"""

import asyncio
import tempfile
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Dict, List

from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright

from database.repositories import UnitOfWork

# ========== НАСТРОЙКА ПУТЕЙ ==========

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates" / "schedule"

# Проверяем существование директории с шаблонами
if not TEMPLATES_DIR.exists():
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    print(f"⚠️ Создана директория для шаблонов: {TEMPLATES_DIR}")

# ========== НАСТРОЙКА JINJA2 ==========

env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========


def format_time(dt: datetime) -> str:
    """Форматирование времени для отображения"""
    return dt.strftime("%H:%M")


def format_date_readable(d: date) -> str:
    """Форматирование даты в читаемый вид"""
    months_ru = {
        1: "января",
        2: "февраля",
        3: "марта",
        4: "апреля",
        5: "мая",
        6: "июня",
        7: "июля",
        8: "августа",
        9: "сентября",
        10: "октября",
        11: "ноября",
        12: "декабря",
    }
    return f"{d.day} {months_ru[d.month]}"


def get_topic_by_group(group_name: str) -> str:
    """Определение направления по названию группы.

    Поддерживает как кириллические, так и латинские обозначения из старых файлов
    (например, ``E-43`` и ``Yu-41``).
    """
    normalized = group_name.upper()
    if normalized.startswith(("Э", "E")):
        return "ЭКОНОМИКА"
    elif normalized.startswith(("М", "M")):
        return "МЕНЕДЖМЕНТ"
    elif normalized.startswith(("Г", "GMU")):
        return "ГМУ"
    elif normalized.startswith(("Ю", "YU")):
        return "ЮРИСПРУДЕНЦИЯ"
    else:
        return group_name


# ========== ОСНОВНЫЕ ФУНКЦИИ ==========


async def render_html(target_date: date, group_name: str) -> str:
    """
    Рендерит HTML расписания для указанной даты и группы

    Args:
        target_date: Дата расписания
        group_name: Название группы

    Returns:
        str: HTML код расписания
    """
    # Получаем данные из БД
    async with UnitOfWork() as uow:
        group = await uow.groups.get_by_name(group_name)
        if not group:
            return f"<html><body><h1>Группа {group_name} не найдена</h1></body></html>"

        lessons = await uow.lessons.get_by_group_and_date(group.group_id, target_date)

    # Подготавливаем данные для шаблона
    lessons_data = []
    lesson_types_map = {
        "Лекция": "ЛЕКЦИЯ",
        "Практика": "ПРАКТИКА",
        "л": "ЛЕКЦИЯ",
        "пр": "ПРАКТИКА",
    }

    for lesson in lessons:
        # Определяем тип занятия
        lesson_type = lesson_types_map.get(
            lesson.lesson_type, "ЗАНЯТИЕ" if lesson.lesson_type else "ЗАНЯТИЕ"
        )

        # Форматируем аудиторию
        classroom = lesson.classroom
        if classroom and classroom[0].isdigit():
            classroom = f"ауд. {classroom}"

        lesson_dict = {
            "subject": lesson.subject.name,
            "teacher": lesson.teacher.name,
            "type": lesson_type,
            "classroom": classroom,
            "start_time": format_time(lesson.start_datetime),
        }
        lessons_data.append(lesson_dict)

    # Определяем направление
    topic = get_topic_by_group(group_name)
    formatted_date = format_date_readable(target_date)

    # Выбираем шаблон
    if lessons_data:
        template_name = "index.html"
    else:
        template_name = "no-schedule/index.html"

    try:
        template = env.get_template(template_name)
    except Exception as e:
        print(f"⚠️ Ошибка загрузки шаблона {template_name}: {e}")
        # Возвращаем простой HTML
        return f"""
        <html>
        <head>
            <meta charset="utf-8">
            <title>Расписание</title>
        </head>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h1>{topic}</h1>
            <h2>Группа: {group_name}</h2>
            <h3>Дата: {formatted_date}</h3>
            {'<p>Занятий нет</p>' if not lessons_data else ''}
            {''.join([f'<div><p>{l["start_time"]} - {l["subject"]} ({l["type"]})</p><p>Преподаватель: {l["teacher"]}</p><p>{l["classroom"]}</p><hr></div>' for l in lessons_data])}
        </body>
        </html>
        """

    # Рендерим шаблон
    html = template.render(
        lessons=lessons_data, date=formatted_date, topic=topic, group=group_name
    )

    return html


async def html_to_image(html: str) -> BytesIO:
    """
    Конвертирует HTML в PNG изображение через Playwright

    Args:
        html: HTML код для рендеринга

    Returns:
        BytesIO: Буфер с PNG изображением

    Raises:
        Exception: При ошибке рендеринга
    """
    # Сохраняем HTML во временный файл. Именованный временный файл исключает
    # гонки между несколькими одновременными запросами на генерацию картинки.
    temp_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", encoding="utf-8", delete=False
    )
    html_path = Path(temp_file.name)

    try:
        with temp_file:
            temp_file.write(html)

        async with async_playwright() as p:
            # Запускаем браузер
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )

            # Создаем страницу с нужными размерами
            page = await browser.new_page(
                viewport={
                    "width": 624,
                    "height": 100,
                }  # Начальная высота, будет автоматически расширена
            )

            # Загружаем HTML
            await page.goto(html_path.as_uri())

            # Ждем полной загрузки
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(500)  # Даем время на рендеринг CSS

            # Делаем скриншот полной страницы
            png_bytes = await page.screenshot(full_page=True, type="png")

            await browser.close()

        # Возвращаем как BytesIO
        buf = BytesIO(png_bytes)
        buf.seek(0)
        return buf

    except Exception as e:
        print(f"❌ Ошибка рендеринга HTML в изображение: {e}")
        raise
    finally:
        # Удаляем временный файл
        if html_path.exists():
            try:
                html_path.unlink()
            except:
                pass


# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ТЕСТИРОВАНИЯ ==========


async def test_render():
    """Тестовая функция для проверки рендеринга"""
    from datetime import date

    print("🧪 Тестирование рендеринга...")

    # Тестируем рендеринг HTML
    html = await render_html(date.today(), "Э-42")
    print(f"✅ HTML сгенерирован ({len(html)} символов)")

    # Тестируем конвертацию в изображение
    try:
        image = await html_to_image(html)
        print(f"✅ Изображение создано ({len(image.getvalue())} байт)")
    except Exception as e:
        print(f"❌ Ошибка создания изображения: {e}")


if __name__ == "__main__":
    asyncio.run(test_render())

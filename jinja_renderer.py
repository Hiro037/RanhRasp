import asyncio
import datetime
import tempfile
from io import BytesIO
from pathlib import Path

import imgkit
from PIL import Image, ImageDraw, ImageFont  # обработка картинки [web:23]
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.types.input_file import BufferedInputFile  # отправка из памяти [web:25]
from html2image import Html2Image
from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright
from playwright.sync_api import sync_playwright

from utils import get_lessons, format_date_readable_manual, format_time

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates" / "schedule"

env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=True,
)

hti = Html2Image(
    output_path=str(TEMPLATES_DIR),
    browser_executable='/usr/bin/chromium',
    custom_flags=['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage']
)


def render_html(date: datetime.date, group: str) -> str:
    lessons = get_lessons(date, group)
    lessons_data = []
    lesson_types = {
        "л": "ЛЕКЦИЯ",
        "пр": "ПРАКТИКА"
    }
    if group.startswith("Э"):
        topic = "ЭКОНОМИКА"
    elif group.startswith("М"):
        topic = "МЕНЕДЖМЕНТ"
    elif group.startswith("Г"):
        topic = "ГМУ"
    elif group.startswith("Ю"):
        topic = "ЮРИСПРУДЕНЦИЯ"
    else:
        topic = group

    for lesson in lessons:
        lesson_type = lesson_types.get(lesson.lesson_type, "ЗАНЯТИЕ")
        if lesson.classroom and lesson.classroom[0].isdigit():
            classroom = "ауд. " + lesson.classroom
        else:
            classroom = lesson.classroom if lesson.classroom else ""

        lesson_dict = {
            "subject": lesson.subject.name,
            "teacher": lesson.teacher.name,
            "type": lesson_type,
            "classroom": classroom,
            "start_time": format_time(lesson.start_datetime),
        }
        lessons_data.append(lesson_dict)
    if len(lessons) != 0:
        template = env.get_template("index.html")
    else:
        template = env.get_template("no-schedule/index.html")
    html = template.render(lessons=lessons_data, date=format_date_readable_manual(date), topic=topic)
    return html


async def html_to_image(html: str) -> BytesIO:
    """
    Рендерит HTML в PNG через headless Chromium (Playwright async).
    Возвращает BytesIO с картинкой.
    """
    # сохраняем отрендеренный HTML во временный файл
    html_path = TEMPLATES_DIR / "_rendered.html"
    html_path.write_text(html, encoding="utf-8")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 624, "height": 6})

        # открываем локальный файл [web:49][web:55]
        await page.goto(html_path.as_uri())
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(1000)

        # скриншот как bytes [web:50][web:61]
        png_bytes = await page.screenshot(full_page=True)
        await browser.close()

    buf = BytesIO(png_bytes)
    buf.seek(0)
    return buf

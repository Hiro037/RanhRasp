import asyncio
from datetime import date, datetime
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright

# ========== НАСТРОЙКА ПУТЕЙ И ШАБЛОНОВ ==========
BASE_DIR = Path(__file__).resolve().parent.parent # Корневая папка проекта
TEMPLATES_DIR = BASE_DIR / "templates" / "schedule"

# Автоматически создаем папки для шаблонов, если их нет
if not TEMPLATES_DIR.exists():
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    (TEMPLATES_DIR / "no-schedule").mkdir(parents=True, exist_ok=True)

env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=True,
    trim_blocks=True,
    lstrip_blocks=True,
)

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ФОРМАТИРОВАНИЯ ==========

def format_time(dt: datetime) -> str:
    """Форматирование времени начала пары."""
    return dt.strftime("%H:%M")

def format_date_readable(d: date) -> str:
    """Форматирование даты на русском языке."""
    months_ru = {
        1: "января", 2: "февраля", 3: "марта", 4: "апреля",
        5: "мая", 6: "июня", 7: "июля", 8: "августа",
        9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
    }
    return f"{d.day} {months_ru[d.month]}"

def get_topic_by_group(group_name: str) -> str:
    """Определение названия направления по первой букве группы (РАНХиГС)."""
    if group_name.startswith("Э"):
        return "ЭКОНОМИКА"
    elif group_name.startswith("М"):
        return "МЕНЕДЖМЕНТ"
    elif group_name.startswith("Г"):
        return "ГМУ"
    elif group_name.startswith("Ю"):
        return "ЮРИСПРУДЕНЦИЯ"
    return group_name

# ========== ОСНОВНАЯ ЛОГИКА РЕНДЕРИНГА ==========

async def render_html(lessons: list, target_date: date, group_name: str) -> str:
    """
    Принимает список объектов оригинальных моделей СУБД из сервисного слоя
    и трансформирует их в HTML-код для Jinja2.
    """
    lessons_data = []
    
    # Расширенный маппинг типов под данные из твоего документа
    lesson_types_map = {
        "Лекция": "ЛЕКЦИЯ",
        "Практика": "ПРАКТИКА",
        "л": "ЛЕКЦИЯ",
        "пр": "ПРАКТИКА",
        "конс": "КОНСУЛЬТАЦИЯ",
        "Зачёт с оценкой.": "ЗАЧЕТ С ОЦЕНКОЙ"
    }

    for lesson in lessons:
        # Безопасно извлекаем тип
        raw_type = lesson.type.strip() if lesson.type else "ЗАНЯТИЕ"
        lesson_type = lesson_types_map.get(raw_type, raw_type.upper())

        # Безопасно парсим аудиторию (учитываем связи SQLAlchemy из Этапа 2)
        classroom_name = lesson.classroom.name if lesson.classroom else "—"
        if classroom_name and classroom_name[0].isdigit():
            classroom_name = f"ауд. {classroom_name}"

        # Собираем словарь для Jinja шаблона
        lesson_dict = {
            "subject": lesson.subject.name if lesson.subject else "Не указан",
            "teacher": lesson.teacher.name if lesson.teacher else "Не указан",
            "type": lesson_type,
            "classroom": classroom_name,
            "start_time": format_time(lesson.start_datetime),
        }
        lessons_data.append(lesson_dict)

    topic = get_topic_by_group(group_name)
    formatted_date = format_date_readable(target_date)

    # Выбор файла шаблона
    template_name = "index.html" if lessons_data else "no-schedule/index.html"

    try:
        template = env.get_template(template_name)
        html = template.render(
            lessons=lessons_data, date=formatted_date, topic=topic, group=group_name
        )
    except Exception as e:
        # Резервный HTML-сэйфлок на случай, если шаблоны стерты с диска
        html = f"""
        <html>
        <head><meta charset="utf-8"></head>
        <body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f4f6f9;">
            <h1 style="color: #1a365d;">{topic}</h1>
            <h2>Группа: {group_name} | Дата: {formatted_date}</h2>
            <hr>
            {"<p style='font-size: 18px; color: #718096;'>💤 Занятий нет</p>" if not lessons_data else ""}
            {"".join([f'<div style="margin-bottom:15px; padding:10px; background:#fff; border-left:4px solid #3182ce;"><h3>{l["start_time"]} - {l["subject"]} ({l["type"]})</h3><p><b>Преподаватель:</b> {l["teacher"]} | <b>{l["classroom"]}</b></p></div>' for l in lessons_data])}
        </body>
        </html>
        """
    return html


async def html_to_image(html: str) -> bytes:
    """
    Рендерит готовую HTML-строку в массив байтов (PNG) через Headless Chromium.
    """
    html_path = TEMPLATES_DIR / "_temp_render.html"

    try:
        # Записываем временный файл для Chromium
        html_path.write_text(html, encoding="utf-8")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )
            # Вьюпорт подстроен под мобильный экран мессенджеров
            page = await browser.new_page(viewport={"width": 600, "height": 150})
            await page.goto(html_path.as_uri())
            
            # Ждем селекторы и стили CSS
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(300)

            # Делаем снимок всей высоты сгенерированной страницы
            png_bytes = await page.screenshot(full_page=True, type="png")
            await browser.close()

        return png_bytes

    except Exception as e:
        print(f"❌ Критическая ошибка Playwright рендеринга: {e}")
        raise
    finally:
        if html_path.exists():
            try:
                html_path.unlink()
            except:
                pass


async def generate_schedule_image(lessons: list, target_date: date, group_name: str) -> bytes:
    """
    Единая точка входа для ботов.
    Принимает сырые данные, возвращает байты картинки готовые к отправке.
    """
    html_content = await render_html(lessons, target_date, group_name)
    image_bytes = await html_to_image(html_content)
    return image_bytes
"""
Render HTML schedule to PNG using Jinja2 and Playwright.
Expects lessons_data: list of dict with keys:
 start_time, subject, teacher, type, classroom, comment, groups (optional)
"""

import asyncio
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import List, Dict

from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates" / "schedule"

if not TEMPLATES_DIR.exists():
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=True,
    trim_blocks=True,
    lstrip_blocks=True
)

async def render_html(target_date: date, group_name: str, lessons_data: List[Dict]) -> str:
    """Render HTML string from template."""
    # format date like "28 мая"
    months_ru = {1: "января", 2: "февраля", 3: "марта", 4: "апреля",
                 5: "мая", 6: "июня", 7: "июля", 8: "августа",
                 9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"}
    formatted_date = f"{target_date.day} {months_ru[target_date.month]}"
    template_name = "index.html" if lessons_data else "no-schedule/index.html"
    try:
        template = env.get_template(template_name)
    except Exception as e:
        # fallback
        return f"<html><body><h1>Error loading template</h1></body></html>"
    html = template.render(
        lessons=lessons_data,
        date=formatted_date,
        topic=group_name,
        group=group_name
    )
    return html

async def html_to_image(html: str) -> bytes:
    """Convert HTML to PNG bytes."""
    html_path = TEMPLATES_DIR / "_temp.html"
    try:
        html_path.write_text(html, encoding="utf-8")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
            page = await browser.new_page(viewport={"width": 624, "height": 100})
            await page.goto(html_path.as_uri())
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(500)
            png_bytes = await page.screenshot(full_page=True, type='png')
            await browser.close()
        return png_bytes
    finally:
        if html_path.exists():
            html_path.unlink()
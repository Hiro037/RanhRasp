#!/usr/bin/env python3
"""
Точка входа для ботов расписания (Telegram + VK).
VK-бот запускается в отдельном потоке со своим циклом asyncio,
чтобы избежать конфликта "Cannot run the event loop while another loop is running".
"""

import asyncio
import logging
import threading

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from database.connection import init_db
from services.daily_notifier import send_daily_notifications
from tg_bot.loader import tg_bot, tg_dp
from utils.timezone import YEKT_TZ
from config import settings
from vk_bot.loader import vk_bot
from tg_bot.handlers import menu, registration, settings_feedback, teacher_action, admin
from vk_bot.handlers import admin as vk_admin, menu as vk_menu, registration as vk_reg, \
    settings_feedback as vk_settings, teacher_action as vk_teacher

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ========== Регистрация роутеров Telegram ==========
tg_dp.include_router(menu.menu_router)
tg_dp.include_router(registration.registration_router)
tg_dp.include_router(settings_feedback.router)
tg_dp.include_router(teacher_action.teacher_router)
tg_dp.include_router(admin.router)

# ========== Регистрация blueprints VK ==========
vk_bot.labeler.load(vk_admin.bp)
vk_bot.labeler.load(vk_menu.vk_menu_labeler)
vk_bot.labeler.load(vk_reg.vk_registration_labeler)
vk_bot.labeler.load(vk_settings.bp)
vk_bot.labeler.load(vk_teacher.vk_teacher_labeler)


async def on_startup():
    """Действия при запуске ботов"""
    logger.info("Инициализация базы данных...")
    await init_db()
    logger.info("База данных готова")

    # Запуск планировщика ежедневных уведомлений
    scheduler = AsyncIOScheduler(timezone=YEKT_TZ)
    if settings.ENABLE_DAILY_NOTIFICATIONS:
        scheduler.add_job(
            send_daily_notifications,
            trigger=CronTrigger(hour=8, minute=0),
            id="daily_notifications",
            replace_existing=True
        )
        scheduler.start()
        logger.info("Планировщик ежедневных уведомлений запущен (каждый день в 8:00)")


def run_vk_bot_in_thread():
    """Запуск VK бота в отдельном потоке с новым изолированным циклом asyncio"""
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # Здесь тоже убираем loop.run_until_complete
    vk_bot.run_polling()


async def main():
    await on_startup()

    # Telegram бот – обычная задача в основном цикле
    tg_task = asyncio.create_task(
        tg_dp.start_polling(tg_bot, allowed_updates=["message", "callback_query"])
    )

    # VK бот – запускаем в отдельном потоке (daemon=True, чтобы завершался вместе с main)
    vk_thread = threading.Thread(target=run_vk_bot_in_thread, daemon=True)
    vk_thread.start()

    logger.info("Боты запущены. Нажмите Ctrl+C для остановки.")

    # Ждём только задачу Telegram (VK-поток живёт фоном)
    await tg_task


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Боты остановлены пользователем.")
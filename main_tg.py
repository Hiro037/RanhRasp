#!/usr/bin/env python3
import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from database.connection import init_db
from services.daily_notifier import send_daily_notifications
from tg_bot.loader import tg_bot, tg_dp
from utils.timezone import YEKT_TZ
from config import settings
from tg_bot.handlers import menu, registration, settings_feedback, teacher_action, admin

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

tg_dp.include_router(menu.menu_router)
tg_dp.include_router(registration.registration_router)
tg_dp.include_router(settings_feedback.router)
tg_dp.include_router(teacher_action.teacher_router)
tg_dp.include_router(admin.router)

async def on_startup():
    logger.info("Инициализация БД...")
    await init_db()
    logger.info("БД готова")
    scheduler = AsyncIOScheduler(timezone=YEKT_TZ)
    if settings.ENABLE_DAILY_NOTIFICATIONS:
        scheduler.add_job(send_daily_notifications, trigger=CronTrigger(hour=8, minute=0),
                          id="daily_notifications", replace_existing=True)
        scheduler.start()
        logger.info("Планировщик запущен")

async def main():
    await on_startup()
    logger.info("Telegram бот запущен")
    await tg_dp.start_polling(tg_bot, allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Остановлен")

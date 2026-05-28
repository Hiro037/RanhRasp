"""
Daily notifications using APScheduler.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Callable, Awaitable
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from core.database import AsyncSessionLocal
from core.services import get_schedule_text_cached, get_schedule_image_cached, get_user_by_id, get_user_role
from core.models import TZ, ScheduleMessageType
from core.utils import get_current_date

scheduler = AsyncIOScheduler()

async def send_daily_notifications(send_callback):
    async with AsyncSessionLocal() as db:
        from core.services import get_all_users_with_notifications, get_user_by_id, get_user_role
        users = await get_all_users_with_notifications(db)
    tomorrow = get_current_date() + timedelta(days=1)
    for user in users:
        text = None
        img = None
        if user.schedule_message_type == ScheduleMessageType.TEXT:
            text = await get_schedule_text_cached(user.id, tomorrow)
        else:
            img = await get_schedule_image_cached(user.id, tomorrow)
        await send_callback(user.id, text, img)

def start_notifier(send_callback: Callable[[int, str, bytes | None], Awaitable[None]]):
    """Start the APScheduler to run daily at 18:00 TZ."""
    trigger = CronTrigger(hour=18, minute=0, timezone=TZ)
    scheduler.add_job(send_daily_notifications, trigger, args=[send_callback])
    scheduler.start()
import asyncio
import os

from aiogram import Dispatcher, Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv

from analytic_db import async_session_maker, init_db
from bot import schedule_bot
from middlewares import DatabaseAnalyticsMiddleware

load_dotenv()

async def main():

    router = schedule_bot.router

    await init_db()

    BOT_TOKEN = os.getenv("BOT_TOKEN")
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(
        parse_mode=ParseMode.HTML,
    ))
    dp = Dispatcher()

    dp.message.middleware(DatabaseAnalyticsMiddleware(async_session_maker))
    dp.callback_query.middleware(DatabaseAnalyticsMiddleware(async_session_maker))

    dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)
    print('Бот запущен')

if __name__ == "__main__":
    asyncio.run(main())

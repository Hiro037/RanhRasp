"""
Главная точка входа для запуска Telegram бота RanhRasp

Основные функции:
- Инициализация асинхронной базы данных
- Настройка middleware для отслеживания пользователей
- Регистрация роутеров
- Запуск бота в режиме long polling

Версия: 2.0.0 (Async)
"""
import asyncio
import logging
import os
import sys
from datetime import datetime

from aiogram import Dispatcher, Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv

from database.models import init_db
from bot import schedule_bot
from middlewares import UserActivityMiddleware, GroupSelectionMiddleware

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========

# Настраиваем базовое логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)

# Создаем логгер для приложения
logger = logging.getLogger(__name__)

# Отключаем излишне подробное логирование библиотек
logging.getLogger("aiogram").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

# ========== ЗАГРУЗКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ==========

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

# Проверка обязательных переменных окружения
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не найден в переменных окружения!")
    logger.error("Создайте файл .env и добавьте BOT_TOKEN=ваш_токен")
    sys.exit(1)

if not ADMIN_ID:
    logger.warning("⚠️ ADMIN_ID не указан. Административные функции будут недоступны.")


# ========== ИНИЦИАЛИЗАЦИЯ БОТА ==========

async def on_startup(bot: Bot):
    """
    Callback, выполняемый при запуске бота

    Выполняет:
    - Инициализацию базы данных
    - Проверку подключения к Telegram API
    - Отправку уведомления администратору
    """
    logger.info("🚀 Запуск бота...")

    # Инициализируем базу данных
    try:
        logger.info("📦 Инициализация базы данных...")
        await init_db()
        logger.info("✅ База данных успешно инициализирована")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")
        raise

    # Получаем информацию о боте
    try:
        bot_info = await bot.get_me()
        logger.info(f"✅ Бот успешно авторизован: @{bot_info.username}")
        logger.info(f"   ID: {bot_info.id}")
        logger.info(f"   Имя: {bot_info.first_name}")
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к Telegram API: {e}")
        raise

    # Отправляем уведомление администратору
    if ADMIN_ID:
        try:
            await bot.send_message(
                ADMIN_ID,
                "🟢 <b>Бот запущен!</b>\n\n"
                f"Время запуска: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
                f"Версия: 2.0.0 (Async)\n"
                f"Бот: @{bot_info.username}"
            )
            logger.info(f"📬 Уведомление отправлено администратору (ID: {ADMIN_ID})")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось отправить уведомление администратору: {e}")

    logger.info("=" * 60)
    logger.info("🎉 БОТ ГОТОВ К РАБОТЕ")
    logger.info("=" * 60)


async def on_shutdown(bot: Bot):
    """
    Callback, выполняемый при остановке бота

    Выполняет:
    - Закрытие соединений
    - Отправку уведомления администратору
    """
    logger.info("🛑 Остановка бота...")

    # Отправляем уведомление администратору
    if ADMIN_ID:
        try:
            await bot.send_message(
                ADMIN_ID,
                "🔴 <b>Бот остановлен</b>\n\n"
                f"Время остановки: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
            )
        except Exception as e:
            logger.warning(f"⚠️ Не удалось отправить уведомление об остановке: {e}")

    logger.info("✅ Бот успешно остановлен")


# ========== ГЛАВНАЯ ФУНКЦИЯ ==========

async def main():
    """
    Главная функция запуска бота

    Выполняет:
    1. Создание экземпляра бота
    2. Создание диспетчера
    3. Регистрацию middleware
    4. Регистрацию роутеров
    5. Настройку startup/shutdown callbacks
    6. Запуск polling
    """

    # Создаем экземпляр бота
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,  # HTML разметка по умолчанию
        )
    )

    # Создаем диспетчер
    dp = Dispatcher()

    # ========== РЕГИСТРАЦИЯ MIDDLEWARE ==========

    logger.info("🔧 Регистрация middleware...")

    # Middleware для отслеживания активности пользователей
    # Выполняется для всех сообщений и callback запросов
    dp.message.middleware(UserActivityMiddleware())
    dp.callback_query.middleware(UserActivityMiddleware())

    # Middleware для автоматической подстановки группы пользователя
    dp.message.middleware(GroupSelectionMiddleware())
    dp.callback_query.middleware(GroupSelectionMiddleware())

    logger.info("✅ Middleware зарегистрированы")

    # ========== РЕГИСТРАЦИЯ РОУТЕРОВ ==========

    logger.info("🔧 Регистрация обработчиков...")

    # Подключаем роутер из bot.py
    dp.include_router(schedule_bot.router)

    logger.info("✅ Обработчики зарегистрированы")

    # ========== РЕГИСТРАЦИЯ STARTUP/SHUTDOWN CALLBACKS ==========

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # ========== ЗАПУСК БОТА ==========

    try:
        # Удаляем webhook и накопившиеся обновления
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("🗑️ Webhook удален, накопившиеся обновления очищены")

        # Запускаем polling
        logger.info("🔄 Запуск long polling...")
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),  # Принимаем только используемые типы обновлений
            polling_timeout=30,  # Таймаут запроса к Telegram API
        )

    except KeyboardInterrupt:
        logger.info("⌨️ Получен сигнал прерывания (Ctrl+C)")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        raise
    finally:
        # Закрываем соединения
        await bot.session.close()
        logger.info("🔌 Соединения закрыты")


# ========== ТОЧКА ВХОДА ==========

if __name__ == "__main__":
    try:
        # Запускаем бота
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Завершение работы по запросу пользователя")
    except Exception as e:
        logger.critical(f"💥 Фатальная ошибка при запуске: {e}", exc_info=True)
        sys.exit(1)

"""
Утилита для запуска всех сервисов RanhRasp

Запускает:
- Telegram бот (main.py)
- FastAPI сервер (api.py)

Использование:
    python start_services.py

Опции:
    --bot-only    - Запустить только бота
    --api-only    - Запустить только API
    --dev         - Режим разработки (автоперезагрузка)
"""

import asyncio
import logging
import multiprocessing
import sys
from typing import Optional

import uvicorn
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

load_dotenv()


def run_bot():
    """Запуск Telegram бота"""
    logger.info("🤖 Запуск Telegram бота...")
    from main import main

    asyncio.run(main())


def run_api(dev_mode: bool = False):
    """
    Запуск FastAPI сервера

    Args:
        dev_mode: Режим разработки с автоперезагрузкой
    """
    logger.info("🌐 Запуск FastAPI сервера...")
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        reload=dev_mode,
        log_level="info",
        access_log=True,
    )


def start_all(dev_mode: bool = False):
    """
    Запуск всех сервисов

    Args:
        dev_mode: Режим разработки
    """
    logger.info("=" * 60)
    logger.info("🚀 ЗАПУСК ВСЕХ СЕРВИСОВ RanhRasp")
    logger.info("=" * 60)

    # Создаем процессы для бота и API
    bot_process = multiprocessing.Process(target=run_bot, name="TelegramBot")
    api_process = multiprocessing.Process(
        target=run_api, args=(dev_mode,), name="FastAPI"
    )

    try:
        # Запускаем процессы
        bot_process.start()
        api_process.start()

        logger.info("✅ Все сервисы запущены")
        logger.info("   🤖 Telegram бот - PID: %d", bot_process.pid)
        logger.info(
            "   🌐 FastAPI сервер - http://0.0.0.0:8000 - PID: %d", api_process.pid
        )
        logger.info("   📚 API документация - http://0.0.0.0:8000/api/docs")
        logger.info("")
        logger.info("Нажмите Ctrl+C для остановки")

        # Ожидаем завершения процессов
        bot_process.join()
        api_process.join()

    except KeyboardInterrupt:
        logger.info("\n⌨️ Получен сигнал прерывания")
        logger.info("🛑 Останавливаем сервисы...")

        # Останавливаем процессы
        if bot_process.is_alive():
            bot_process.terminate()
            bot_process.join(timeout=5)
            if bot_process.is_alive():
                bot_process.kill()

        if api_process.is_alive():
            api_process.terminate()
            api_process.join(timeout=5)
            if api_process.is_alive():
                api_process.kill()

        logger.info("✅ Все сервисы остановлены")

    except Exception as e:
        logger.error("❌ Ошибка при запуске: %s", e, exc_info=True)
        sys.exit(1)


def main():
    """Главная функция"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Запуск сервисов RanhRasp",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  python start_services.py              # Запустить все сервисы
  python start_services.py --bot-only   # Только бот
  python start_services.py --api-only   # Только API
  python start_services.py --dev        # Режим разработки
        """,
    )

    parser.add_argument(
        "--bot-only", action="store_true", help="Запустить только Telegram бота"
    )

    parser.add_argument(
        "--api-only", action="store_true", help="Запустить только FastAPI сервер"
    )

    parser.add_argument(
        "--dev", action="store_true", help="Режим разработки (автоперезагрузка для API)"
    )

    args = parser.parse_args()

    # Проверка взаимоисключающих опций
    if args.bot_only and args.api_only:
        logger.error("❌ Нельзя использовать --bot-only и --api-only одновременно")
        sys.exit(1)

    # Запускаем сервисы в зависимости от параметров
    if args.bot_only:
        run_bot()
    elif args.api_only:
        run_api(dev_mode=args.dev)
    else:
        start_all(dev_mode=args.dev)


if __name__ == "__main__":
    # Для Windows необходимо
    multiprocessing.freeze_support()
    main()

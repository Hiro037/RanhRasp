from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import settings
from tg_bot.middlewares import TgLoggingMiddleware

# Инициализируем бот и диспетчер (хранилище FSM в памяти)
tg_bot = Bot(token=settings.TG_TOKEN)
tg_dp = Dispatcher(storage=MemoryStorage())

# Регистрируем Middleware логирования на любые текстовые сообщения
tg_dp.message.outer_middleware(TgLoggingMiddleware())

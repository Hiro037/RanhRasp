import asyncio

from vkbottle.bot import Bot
from config import settings
from vk_bot.middlewares import VkLoggingMiddleware

vk_bot = Bot(token=settings.VK_TOKEN)

# Регистрация middleware (без вызова экземпляра, передаётся класс)
vk_bot.labeler.message_view.register_middleware(VkLoggingMiddleware)

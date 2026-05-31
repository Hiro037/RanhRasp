from vkbottle.bot import Bot
from config import settings
from vk_bot.middlewares import VkLoggingMiddleware

# Создаем объект бота VK
vk_bot = Bot(token=settings.VK_TOKEN)

# Регистрируем Middleware логирования
vk_bot.labeler.message_view.register_middleware(VkLoggingMiddleware())

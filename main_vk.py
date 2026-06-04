import asyncio
import logging

from database.connection import init_db
from vk_bot.loader import vk_bot
from vk_bot.handlers import admin as vk_admin, menu as vk_menu, registration as vk_reg, settings_feedback as vk_settings, teacher_action as vk_teacher

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

vk_bot.labeler.load(vk_admin.bp)
vk_bot.labeler.load(vk_menu.vk_menu_labeler)
vk_bot.labeler.load(vk_reg.vk_registration_labeler)
vk_bot.labeler.load(vk_settings.bp)
vk_bot.labeler.load(vk_teacher.vk_teacher_labeler)

async def main():
    logger.info("Инициализация БД...")
    await init_db()


if __name__ == "__main__":
    # asyncio.run(main())
    logger.info("VK бот запущен")
    vk_bot.run_forever()

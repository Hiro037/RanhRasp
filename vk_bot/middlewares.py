from vkbottle import BaseMiddleware
from vkbottle.bot import Message

from database.connection import async_session_maker
from services.log_service import add_log_entry
from services.user_service import get_user_by_platform_id
from config import settings


class VkLoggingMiddleware(BaseMiddleware[Message]):
    async def pre(self):
        # Метод выполняется ДО того, как сообщение попадет в хендлеры
        async with async_session_maker() as session:
            user = await get_user_by_platform_id(session, "vk", self.event.from_id)
            user_id = user.id if user else None

            # Определяем роль
            if self.event.from_id in settings.VK_ADMINS:
                user_role = "admin"
            elif user and user.teacher_profile_id is not None:
                user_role = "teacher"
            elif user:
                user_role = "student"
            else:
                user_role = "guest"

            action = self.event.text or "[Вложение/Кнопка]"

            # Записываем входящее действие
            await add_log_entry(
                session=session,
                platform="vk",
                action_type=f"msg: {action[:40]}",
                status="success",
                user_id=user_id,
                platform_user_id=self.event.from_id,
                user_role=user_role
            )
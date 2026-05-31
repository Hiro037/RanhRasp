from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message

from database.connection import async_session
from services.log_service import add_log_entry
from services.user_service import get_user_by_platform_id
from config import settings


class TgLoggingMiddleware(BaseMiddleware):
    async def __call__(
            self,
            handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
            event: Message,
            data: Dict[str, Any]
    ) -> Any:
        # Логируем только текстовые сообщения или команды
        if not isinstance(event, Message):
            return await handler(event, data)

        async with async_session() as session:
            # 1. Пытаемся найти пользователя в нашей БД
            user = await get_user_by_platform_id(session, "tg", event.from_user.id)
            user_id = user.id if user else None

            # 2. Определяем роль пользователя
            if event.from_user.id in settings.TG_ADMINS:
                user_role = "admin"
            elif user and user.teacher_profile_id is not None:
                user_role = "teacher"
            elif user:
                user_role = "student"
            else:
                user_role = "guest"

            action = event.text or "[Вложение/Кнопка]"

            # 3. Запускаем хендлер и смотрим на результат
            try:
                result = await handler(event, data)

                # Если все прошло успешно — записываем лог
                await add_log_entry(
                    session=session,
                    platform="tg",
                    action_type=f"msg: {action[:40]}",
                    status="success",
                    user_id=user_id,
                    platform_user_id=event.from_user.id,
                    user_role=user_role
                )
                return result

            except Exception as e:
                # Если в коде хендлера произошла ошибка — фиксируем её в БД
                await add_log_entry(
                    session=session,
                    platform="tg",
                    action_type=f"msg: {action[:40]}",
                    status="error",
                    user_id=user_id,
                    platform_user_id=event.from_user.id,
                    user_role=user_role,
                    details=str(e)[:900]
                )
                raise e  # Пробрасываем ошибку дальше, чтобы работал логгер python

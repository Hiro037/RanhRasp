"""
Middleware для логирования активности пользователей
"""

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from database.repositories import UnitOfWork


class UserActivityMiddleware(BaseMiddleware):
    """
    Middleware для отслеживания активности пользователей

    - Создает пользователя при первом взаимодействии
    - Обновляет время последней активности
    - Логирует запросы для аналитики
    """

    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any],
    ) -> Any:
        user_obj = data.get("event_from_user")

        if user_obj:
            async with UnitOfWork() as uow:
                # Получаем или создаем пользователя
                user, created = await uow.users.get_or_create(
                    user_id=user_obj.id, username=user_obj.username
                )

                # Определяем тип события
                event_type = type(event).__name__

                # Получаем данные запроса
                if isinstance(event, Message):
                    request_data = event.text
                    request_type = f"message_{event.content_type}"
                elif isinstance(event, CallbackQuery):
                    request_data = event.data
                    request_type = f"callback_{event.data.split('_')[0] if event.data else 'unknown'}"
                else:
                    request_data = None
                    request_type = "unknown"

                # Логируем запрос
                await uow.user_requests.create(
                    user_id=user.id,
                    request_type=request_type,
                    request_data=request_data,
                    group_snapshot=user.group.group_name if user.group else None,
                    telegram_id=user.user_id,
                    username=user.username,
                )

                # Обновляем активность
                await uow.users.update_activity(user.user_id)

                # Сохраняем изменения
                await uow.commit()

                # Добавляем пользователя в data для обработчиков
                data["db_user"] = user

        return await handler(event, data)


class GroupSelectionMiddleware(BaseMiddleware):
    """
    Middleware для автоматической подстановки группы пользователя

    Если пользователь выбрал группу ранее, подставляет ее автоматически
    """

    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any],
    ) -> Any:
        db_user = data.get("db_user")

        if db_user and db_user.group:
            data["user_group"] = db_user.group

        return await handler(event, data)

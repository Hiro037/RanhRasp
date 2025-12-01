from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from typing import Callable, Dict, Any, Awaitable

from analytic_db import UserRequestLog


class DatabaseAnalyticsMiddleware(BaseMiddleware):
    def __init__(self, session_maker):
        super().__init__()
        self.session_maker = session_maker

    async def __call__(
            self,
            handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
            event: Message | CallbackQuery,
            data: Dict[str, Any]
    ) -> Any:
        user = data.get('event_from_user')

        if user:
            async with self.session_maker() as session:
                log_entry = UserRequestLog(
                    user_id=user.id,
                    username=user.username,
                    event_type=type(event).__name__,
                    text=getattr(event, 'text', None),
                    chat_id=getattr(event.chat, 'id', None) if hasattr(event, 'chat') else None
                )
                session.add(log_entry)
                await session.commit()

        return await handler(event, data)

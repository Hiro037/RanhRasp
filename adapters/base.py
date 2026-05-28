"""
Abstract base class for bot adapters.
"""

from abc import ABC, abstractmethod

class BotAdapter(ABC):
    @abstractmethod
    async def send_message(self, user_id: int, text: str, keyboard=None) -> bool:
        pass

    @abstractmethod
    async def send_photo(self, user_id: int, photo_bytes: bytes, caption: str = "") -> bool:
        pass

    @abstractmethod
    async def ask_question(self, user_id: int, text: str, options: list, callback_prefix: str) -> None:
        pass
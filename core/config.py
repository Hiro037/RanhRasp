"""
Configuration management using Pydantic.
"""

import os
from typing import List
from dotenv import load_dotenv
from pydantic import BaseModel, field_validator

load_dotenv()

class Settings(BaseModel):
    # PostgreSQL
    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_user: str = os.getenv("POSTGRES_USER", "schedule_user")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "")
    postgres_db: str = os.getenv("POSTGRES_DB", "schedule_bot")

    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    # Redis
    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_db: int = int(os.getenv("REDIS_DB", "0"))

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # Telegram
    tg_bot_token: str = os.getenv("TG_BOT_TOKEN", "")

    # VK
    vk_group_token: str = os.getenv("VK_GROUP_TOKEN", "")
    vk_group_id: int = int(os.getenv("VK_GROUP_ID", "0"))

    # Admin
    admin_tg_ids: List[int] = []
    admin_vk_ids: List[int] = []

    @field_validator("admin_tg_ids", mode="before")
    @classmethod
    def parse_admin_tg_ids(cls, v):
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return v

    @field_validator("admin_vk_ids", mode="before")
    @classmethod
    def parse_admin_vk_ids(cls, v):
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return v

    # Timezone
    timezone: str = os.getenv("TIMEZONE", "Asia/Yekaterinburg")

settings = Settings()